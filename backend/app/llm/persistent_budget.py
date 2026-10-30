"""跨轮/重启的用量账本。软阈值：最多单次响应越线，后续请求被阻止。

每次外部尝试前持久化pending，响应后立即结算；业务事务回滚不撤销真实用量。
进程崩溃或缺失usage不伪装为0；配置预算时未知用量阻止后续调用。
"""
import hashlib
import uuid
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.llm.budget import TokenBudget
from app.llm.errors import BudgetExceeded
from app.models.entities import LLMBudgetUsage


class PersistentBudget:
    def __init__(self, factory, kind, resource_id, settings):
        self.factory, self.key = factory, (kind, resource_id)
        self.identity = hashlib.sha256((settings.llm_base_url + "|" + settings.llm_model).encode()).hexdigest()
        policy = dict(limit_tokens=settings.llm_budget_tokens_per_interview,
            limit_cost=settings.llm_budget_cost_per_interview,
            price_input_per_million=settings.llm_price_input_per_million,
            price_output_per_million=settings.llm_price_output_per_million,
            identity=self.identity)
        with factory() as db:
            if db.get(LLMBudgetUsage, self.key) is None:
                db.add(LLMBudgetUsage(resource_kind=kind, resource_id=resource_id, policy=policy))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()  # 另一个请求已初始化同一资源。

    @property
    def used_tokens(self):
        with self.factory() as db:
            return db.get(LLMBudgetUsage, self.key).used_tokens

    def begin_call(self):
        with self.factory() as db:
            row = db.get(LLMBudgetUsage, self.key)
            policy = dict(row.policy)
            if policy.pop("identity") != self.identity:
                raise BudgetExceeded("模型配置已变化，请恢复原配置或创建新面试")
            meter = TokenBudget(**policy, used_tokens=row.used_tokens, used_cost=row.used_cost)
            meter.check()
            if row.pending:
                raise BudgetExceeded("存在进行中或未结算的模型请求，请核对用量后再继续")
            if meter.enabled and row.unknown_calls:
                raise BudgetExceeded("存在未知模型用量，预算已暂停，请核对供应商账单")
            call_id = uuid.uuid4().hex
            result = db.execute(update(LLMBudgetUsage).where(
                LLMBudgetUsage.resource_kind == self.key[0], LLMBudgetUsage.resource_id == self.key[1],
                LLMBudgetUsage.version == row.version, LLMBudgetUsage.pending.is_(None)
            ).values(pending=call_id, version=row.version + 1), execution_options={"synchronize_session":False})
            if result.rowcount != 1:
                raise BudgetExceeded("模型预算正在结算，请稍后同步")
            db.commit()
            return call_id

    def finish_call(self, call_id, usage):
        exceeded = False
        with self.factory() as db:
            row = db.get(LLMBudgetUsage, self.key)
            if row.pending != call_id:
                raise BudgetExceeded("模型用量结算编号不匹配")
            policy = dict(row.policy)
            policy.pop("identity")
            meter = TokenBudget(**policy, used_tokens=row.used_tokens, used_cost=row.used_cost)
            unknown = row.unknown_calls
            if usage is None:
                unknown += 1
                exceeded = meter.enabled
            else:
                try:
                    meter.charge(tokens_in=usage[0], tokens_out=usage[1])
                except BudgetExceeded:
                    exceeded = True
            result = db.execute(update(LLMBudgetUsage).where(
                LLMBudgetUsage.resource_kind == self.key[0], LLMBudgetUsage.resource_id == self.key[1],
                LLMBudgetUsage.version == row.version, LLMBudgetUsage.pending == call_id
            ).values(used_tokens=meter.used_tokens, used_cost=meter.used_cost,
                     unknown_calls=unknown, pending=None, version=row.version+1),
                execution_options={"synchronize_session":False})
            if result.rowcount != 1:
                raise BudgetExceeded("模型用量结算冲突，请核对账本")
            db.commit()
        if exceeded:
            raise BudgetExceeded("模型预算耗尽或用量未知，本轮未提交；后续调用已阻止")


def usage_snapshot(db, kind, resource_id):
    row = db.get(LLMBudgetUsage, (kind, resource_id))
    if row is None:
        return {"status":"not_used", "used_tokens":0}
    policy = dict(row.policy)
    policy.pop("identity")
    result = TokenBudget(**policy, used_tokens=row.used_tokens, used_cost=row.used_cost).snapshot()
    return {**result, "version":row.version, "pending":bool(row.pending), "unknown_calls":row.unknown_calls,
            "note":"按响应usage记账，软阈值允许单次越线；金额为配置单价计算值，非供应商账单"}


def reconcile(factory, kind, resource_id, *, version, total_tokens, total_cost):
    """仅供运维停旧worker、核实供应商用量后执行；CAS防止覆盖新账目。"""
    import math
    if type(total_tokens) is not int or total_tokens < 0 or not math.isfinite(total_cost) or total_cost < 0:
        raise ValueError("invalid_totals")
    with factory() as db:
        row = db.get(LLMBudgetUsage, (kind, resource_id))
        if row is None or total_tokens < row.used_tokens or total_cost < row.used_cost:
            raise ValueError("cannot_reduce_known_usage")
        result = db.execute(update(LLMBudgetUsage).where(
            LLMBudgetUsage.resource_kind == kind, LLMBudgetUsage.resource_id == resource_id,
            LLMBudgetUsage.version == version
        ).values(used_tokens=total_tokens, used_cost=total_cost, unknown_calls=0,
                 pending=None, version=version+1), execution_options={"synchronize_session":False})
        if result.rowcount != 1:
            raise ValueError("stale_version")
        db.commit()
