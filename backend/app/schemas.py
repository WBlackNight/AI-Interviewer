"""API 请求/响应 Schema（pydantic v2）。"""
from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, field_validator, TypeAdapter
from typing import Literal, Annotated

from app.voice.audio import MAX_FRAME_BASE64_CHARS


class ResumeCreateRequest(BaseModel):
    name: str = Field(default="匿名用户", max_length=64)
    resume_text: str = Field(default="", max_length=20000)
    # PDF 二进制走 multipart 上传接口；此处文本直传（脚手架主路径）


class ResumeResponse(BaseModel):
    access_token: str | None
    account_owned: bool = False
    resume_id: str
    user_id: str
    skills: list[str]
    projects: list[str]
    education: str


class InterviewCreateRequest(BaseModel):
    resume_id: str | None = None
    position: str = Field(default="java_backend")
    difficulty: str = Field(default="mid", pattern="^(easy|mid|hard)$")
    # 省略为常规面试；显式空列表无效，避免误建为全岗位面试。
    themes: list[Annotated[str, Field(min_length=1, max_length=64)]] | None = Field(
        default=None, min_length=1, max_length=12)


class PlanItemOut(BaseModel):
    theme: str
    weight: float
    difficulty: str
    question_count: int
    include_coding: bool


class InterviewCreateResponse(BaseModel):
    access_token: str | None
    account_owned: bool = False
    interview_id: str
    position: str
    plan: list[PlanItemOut]
    ws_url: str


class RevisionPracticeResponse(InterviewCreateResponse):
    revision_task_id: str
    reused: bool


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class InterviewCancelResponse(BaseModel):
    interview_id: str
    status: Literal["cancelled"] = "cancelled"
    changed: bool
    version: int
    report_url: str


class HealthResponse(BaseModel):
    process_id: int
    status: str
    app_name: str
    llm_enabled: bool
    sandbox_enabled: bool
    question_count: int


class WSMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StartMessage(WSMessage):
    type: Literal["start"]


class AnswerMessage(WSMessage):
    type: Literal["answer"]
    message_id: str = Field(min_length=1, max_length=64, pattern="^[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern="^[a-f0-9]{32}$")
    version: int = Field(ge=0)
    text: str = Field(default="", max_length=20000)
    code: str | None = Field(default=None, max_length=16384)

    @field_validator("code")
    @classmethod
    def code_size(cls, value):
        if value and len(value.encode("utf-8")) > 16384:
            raise ValueError("代码超过16KiB")
        return value


class InterruptMessage(WSMessage):
    """打断当前播报。

    ``utterance_id`` 可缺省：用户可能在任何 tts_chunk 到达之前就开口
    （打断检测先于首包），此时客户端还不知道 utterance 编号。
    """

    type: Literal["interrupt"]
    utterance_id: str | None = Field(default=None, max_length=64, pattern="^[A-Za-z0-9_-]+$")


class AudioMessage(WSMessage):
    """一个上行音频网络帧。

    规格由评审固定（步骤 1.1）：16kHz / 单声道 / PCM s16le / 100ms
    = 1600 样本 = 3200 字节 = base64 4268 字符。此处用 Literal 锁死
    格式与采样率——服务端不做重采样，非 16k 输入必须由客户端转换。
    """

    type: Literal["audio"]
    turn_id: str = Field(pattern="^[a-f0-9]{32}$")
    seq: int = Field(ge=0, le=1_000_000)
    format: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1
    data: str = Field(min_length=4, max_length=MAX_FRAME_BASE64_CHARS)


class AudioEndMessage(WSMessage):
    """客户端主动结束本段发言（VAD 判定的补充手段，例如松开按键）。"""

    type: Literal["audio_end"]
    turn_id: str = Field(pattern="^[a-f0-9]{32}$")


class ReadQuestionMessage(WSMessage):
    """只播报服务端保存的当前题，不接收任意合成文本。"""
    type: Literal["read_question"]
    turn_id: str = Field(pattern="^[a-f0-9]{32}$")
    version: int = Field(ge=0)


incoming_message = TypeAdapter(
    Annotated[
        StartMessage | AnswerMessage | InterruptMessage | AudioMessage | AudioEndMessage | ReadQuestionMessage,
        Field(discriminator="type"),
    ]
)
