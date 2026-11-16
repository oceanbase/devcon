"""模型推荐的共同输出结构；片名、来源始终从真实检索记录读取。"""

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    id: str = Field(description="检索工具实际返回的电影 ID。")
    reason: str = Field(min_length=1, max_length=240, description="用一句话依据工具返回的剧情或字段说明推荐理由，不补充资料以外的事实或评价。")
    evidence_quote: str = Field(min_length=10, max_length=120, description="从这部电影的 overview 中逐字摘录连续的 10 至 120 个字符，作为推荐理由的剧情依据，不改写或加省略号。")


class RecommendationAnswer(BaseModel):
    recommendations: list[Recommendation] = Field(max_length=5)
    message: str = Field(min_length=1, description="简短中文说明；没有匹配电影或数量不足时说明实际情况。")
