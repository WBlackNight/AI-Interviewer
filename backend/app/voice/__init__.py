"""语音链路（P1）。

模块分工：
- ``audio``    帧编解码与校验（16k/单声道/s16le/100ms）
- ``vad``      VAD 与前置音频缓冲
- ``asr``      识别会话（start/feed/finish/close）
- ``tts``      合成（PCM 分片，采样率协议明示）
- ``utterance``切句与文本流抽象
- ``channel``  上行：音频帧 → 文本
- ``playback`` 下行：事件 → TTS 分片 → 有界队列
"""
