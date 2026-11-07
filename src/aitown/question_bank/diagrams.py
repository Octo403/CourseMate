"""Typed, non-executable drawing data for mathematical explanation figures."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DrawingModel(BaseModel):
    model_config = {'extra': 'forbid', 'allow_inf_nan': False}


class DiagramPoint(DrawingModel):
    id: str = Field(min_length=1, max_length=40)
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    label: str = Field(max_length=80)


class DiagramEdge(DrawingModel):
    start: str
    end: str
    label: str = Field(max_length=80)
    directed: bool
    dashed: bool


class DiagramCircle(DrawingModel):
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    radius: float = Field(gt=0, le=50)
    label: str = Field(max_length=80)


class SolutionDiagram(DrawingModel):
    title: str = Field(min_length=1, max_length=120)
    purpose: Literal['problem', 'example']
    caption: str = Field(min_length=1, max_length=400)
    points: list[DiagramPoint] = Field(max_length=30)
    edges: list[DiagramEdge] = Field(max_length=60)
    circles: list[DiagramCircle] = Field(max_length=10)

    @model_validator(mode='after')
    def valid_geometry(self):
        ids = [point.id for point in self.points]
        if len(set(ids)) != len(ids):
            raise ValueError('示意图中的点 ID 不能重复。')
        if any(edge.start not in ids or edge.end not in ids for edge in self.edges):
            raise ValueError('示意图的连线必须引用已定义的点。')
        if not self.points and not self.circles:
            raise ValueError('示意图没有可绘制的内容。')
        if any(c.x-c.radius < 0 or c.x+c.radius > 100
               or c.y-c.radius < 0 or c.y+c.radius > 100 for c in self.circles):
            raise ValueError('示意圆必须完整位于画布内。')
        return self
