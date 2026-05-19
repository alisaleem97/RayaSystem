# app/models/formula.py
# Formula and FormulaItem models.

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

from app.models.department import Parameter


class Formula(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    formula_name: str
    main_test_id: int = Field(foreign_key="testdefinition.id")
    main_parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    gender_type: str = Field(default="both")
    formula_expression: str = Field(default="")
    formula_description: Optional[str] = None
    is_active: bool = Field(default=True)

    created_by: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.now)
    edited_by: Optional[int] = Field(default=None, foreign_key="user.id")
    edited_at: Optional[datetime] = None
    deleted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    deleted_at: Optional[datetime] = None

    main_test: "TestDefinition" = Relationship()
    main_parameter: Optional[Parameter] = Relationship()
    items: List["FormulaItem"] = Relationship(back_populates="formula")


class FormulaItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    formula_id: int = Field(foreign_key="formula.id")
    operation: str = Field(default="+")
    source_type: str = Field(default="parameter")
    source_test_id: Optional[int] = Field(default=None, foreign_key="testdefinition.id")
    source_parameter_id: Optional[int] = Field(default=None, foreign_key="parameter.id")
    weight_value: float = Field(default=1.0)
    order_index: int = Field(default=0)

    formula: Formula = Relationship(back_populates="items")
