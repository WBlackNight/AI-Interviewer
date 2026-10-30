"""Judge0真实服务探测；默认只读，--execute显式执行4个合成程序。

无JUDGE0_URL退出2=未验证。检查配置不等于证明隔离；不会在宿主执行代码。
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import httpx
from app.config import Settings
from app.domain import TestCase
from app.sandbox.judge0 import Judge0Sandbox


def probe(settings, execute=False):
    if not settings.judge0_url:
        return {'status':'not_configured','execution_verified':False}, 2
    judge=Judge0Sandbox(settings.judge0_url,api_key=settings.judge0_api_key,
                        language_id=settings.judge0_language_id)
    report={'status':'failed','execution_verified':False,'isolation_verified':False}
    try:
        with httpx.Client(trust_env=False,timeout=10) as client:
            config=judge.request_json(client,'GET',settings.judge0_url.rstrip('/')+'/config_info',timeout=10)
            language=judge.request_json(client,'GET',settings.judge0_url.rstrip('/')+f'/languages/{settings.judge0_language_id}',timeout=10)
        checks={'network_default_disabled':config.get('enable_network') is False,
                'network_override_disabled':config.get('allow_enable_network') is False,
                'language_is_python':isinstance(language.get('name'),str) and 'Python' in language['name']}
        report['checks']=checks
        if not all(checks.values()):return report,1
        if execute:
            cases=[('accepted','print(42)',3),('wrong_answer','print(0)',4),
                   ('timeout','while True: pass',5),('syntax_error','def broken(',6)]
            outcomes=[]
            for name,code,expected in cases:
                result=judge.judge(code,[TestCase('', '42')])
                status=result.detail[0]['status_id']
                outcomes.append({'name':name,'expected_status':expected,'actual_status':status,'passed':status==expected})
            report['executions']=outcomes
            report['execution_verified']=all(row['passed'] for row in outcomes)
            if not report['execution_verified']:return report,1
        report['status']='passed' if execute else 'config_checked_only'
        return report,0
    except Exception as exc:
        report['error_category']=type(exc).__name__
        return report,1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    settings=Settings(_env_file=Path(__file__).resolve().parents[1]/'backend/.env')
    report,code=probe(settings,args.execute)
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(encoded+'\n',encoding='utf-8')
    print(encoded)
    return code


if __name__=='__main__':sys.exit(main())
