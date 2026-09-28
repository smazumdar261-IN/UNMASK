"""TypeScript AST node definitions.

Per Section 13 of the Master Specification (Phase 7: TypeScript):
Defines TypeScript-specific AST nodes preserving:
- Interfaces (TSInterfaceDeclaration, TSPropertySignature, TSMethodSignature)
- Type aliases (TSTypeAliasDeclaration, TSTypeAnnotation)
- Enums (TSEnumDeclaration, TSEnumMember)
- Generics (TSTypeParameterDeclaration, TSTypeParameter)
- Type assertions (TSAsExpression)
- Decorators (TSDecorator)
- Type annotations on variables and function signatures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from languages.javascript.ast_nodes import *


@dataclass
class TSType(JSNode):
    """Base class for TypeScript type annotations."""


@dataclass
class TSTypeAnnotation(TSType):
    """Type annotation (e.g. : string, : Array<T>, : string[])."""

    type_name: str = ""
    type_arguments: List[Any] = field(default_factory=list)
    is_array: bool = False
    raw: str = ""


@dataclass
class TSTypeParameter(JSNode):
    """Generic type parameter declaration (e.g. T in <T extends Base = Default>)."""

    name: str = ""
    constraint: Optional[Any] = None
    default: Optional[Any] = None


@dataclass
class TSTypeParameterDeclaration(JSNode):
    """Type parameter list (e.g. <T, U>)."""

    params: List[TSTypeParameter] = field(default_factory=list)


@dataclass
class TSPropertySignature(JSNode):
    """Interface property signature: [readonly] key[?] : Type;."""

    key: JSIdentifier = field(default_factory=JSIdentifier)
    type_annotation: Optional[TSTypeAnnotation] = None
    optional: bool = False
    readonly: bool = False


@dataclass
class TSMethodSignature(JSNode):
    """Interface method signature: key<T>(param: Type): ReturnType;."""

    key: JSIdentifier = field(default_factory=JSIdentifier)
    params: List[Any] = field(default_factory=list)
    return_type: Optional[TSTypeAnnotation] = None
    type_parameters: Optional[TSTypeParameterDeclaration] = None


@dataclass
class TSInterfaceDeclaration(JSStatement):
    """Interface declaration: interface Name<T> extends Base { ... }."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    type_parameters: Optional[TSTypeParameterDeclaration] = None
    extends: List[Any] = field(default_factory=list)
    body: List[Any] = field(default_factory=list)


@dataclass
class TSTypeAliasDeclaration(JSStatement):
    """Type alias declaration: type Name<T> = TypeAnnotation;."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    type_parameters: Optional[TSTypeParameterDeclaration] = None
    type_annotation: Optional[TSTypeAnnotation] = None


@dataclass
class TSEnumMember(JSNode):
    """Enum member: Name = Value or Name."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    initializer: Optional[JSExpression] = None


@dataclass
class TSEnumDeclaration(JSStatement):
    """Enum declaration: [const] enum Name { Member1 = 1, Member2 }."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    members: List[TSEnumMember] = field(default_factory=list)
    is_const: bool = False


@dataclass
class TSAsExpression(JSExpression):
    """Type assertion: expr as Type."""

    expression: JSExpression = field(default_factory=JSExpression)
    type_annotation: Optional[TSTypeAnnotation] = None


@dataclass
class TSDecorator(JSNode):
    """Decorator: @expr or @expr(args)."""

    expression: JSExpression = field(default_factory=JSExpression)


@dataclass
class TSParameter(JSExpression):
    """Typed parameter: name?: Type = default."""

    id: JSIdentifier = field(default_factory=JSIdentifier)
    type_annotation: Optional[TSTypeAnnotation] = None
    optional: bool = False
    default: Optional[JSExpression] = None
