"""Go AST node definitions.

Per Section 15 of the Master Specification (Phase 9: Go):
Defines the Abstract Syntax Tree structure for Go source files,
including packages, imports, declarations, functions, statements, and expressions.
All nodes inherit from GoNode and maintain SourceLocation provenance.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.provenance import SourceLocation


@dataclass
class GoNode(ABC):
    """Base class for all Go AST nodes."""

    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass
class GoExpression(GoNode):
    """Base class for all Go expressions."""


@dataclass
class GoStatement(GoNode):
    """Base class for all Go statements."""


@dataclass
class GoDecl(GoNode):
    """Base class for all Go declarations (type, const, var, func)."""


# Top-level nodes

@dataclass
class GoImportSpec(GoNode):
    """Import specification: [alias] "path"."""

    path: str = ""
    name: Optional[str] = None  # alias, or None, or "." or "_"


@dataclass
class GoFile(GoNode):
    """Root node for a Go source file."""

    package: str = "main"
    imports: List[GoImportSpec] = field(default_factory=list)
    decls: List[GoDecl] = field(default_factory=list)


# Declarations

@dataclass
class GoField(GoNode):
    """Field or parameter: [name] type."""

    name: str = ""
    type_name: str = "any"


@dataclass
class GoConstSpec(GoDecl):
    """Constant declaration: const name [type] = val."""

    names: List[str] = field(default_factory=list)
    type_name: Optional[str] = None
    values: List[GoExpression] = field(default_factory=list)


@dataclass
class GoVarSpec(GoDecl):
    """Variable declaration: var name [type] [= val]."""

    names: List[str] = field(default_factory=list)
    type_name: Optional[str] = None
    values: List[GoExpression] = field(default_factory=list)


@dataclass
class GoTypeDecl(GoDecl):
    """Type declaration: type Name [=] TypeDefinition."""

    name: str = ""
    is_alias: bool = False
    type_def: str = ""


@dataclass
class GoFunctionDecl(GoDecl):
    """Function or method declaration: func [(recv)] Name(params) [results] { body }."""

    name: str = ""
    receiver: Optional[GoField] = None
    params: List[GoField] = field(default_factory=list)
    results: List[GoField] = field(default_factory=list)
    body: Optional[GoBlock] = None


# Statements

@dataclass
class GoBlock(GoStatement):
    """Block of statements enclosed in braces: { ... }."""

    statements: List[GoStatement] = field(default_factory=list)


@dataclass
class GoExpressionStatement(GoStatement):
    """Statement consisting of an expression: expr."""

    expression: GoExpression = field(default_factory=GoExpression)


@dataclass
class GoAssignmentStatement(GoStatement):
    """Assignment statement: left := right or left = right or left += right."""

    left: List[GoExpression] = field(default_factory=list)
    operator: str = ":="
    right: List[GoExpression] = field(default_factory=list)


@dataclass
class GoIfStatement(GoStatement):
    """If statement: if [init;] cond { body } [else else_branch]."""

    init: Optional[GoStatement] = None
    condition: GoExpression = field(default_factory=GoExpression)
    body: GoBlock = field(default_factory=GoBlock)
    else_branch: Optional[GoStatement] = None  # GoBlock or GoIfStatement


@dataclass
class GoForStatement(GoStatement):
    """For loop: for [init;] [cond;] [post] { body }."""

    init: Optional[GoStatement] = None
    condition: Optional[GoExpression] = None
    post: Optional[GoStatement] = None
    body: GoBlock = field(default_factory=GoBlock)


@dataclass
class GoRangeStatement(GoStatement):
    """Range loop: for key, val := range expr { body }."""

    key: Optional[GoExpression] = None
    value: Optional[GoExpression] = None
    operator: str = ":="
    expression: GoExpression = field(default_factory=GoExpression)
    body: GoBlock = field(default_factory=GoBlock)


@dataclass
class GoReturnStatement(GoStatement):
    """Return statement: return [exprs]."""

    results: List[GoExpression] = field(default_factory=list)


@dataclass
class GoBranchStatement(GoStatement):
    """Branch statement: break, continue, goto, fallthrough [label]."""

    token: str = "break"
    label: Optional[str] = None


@dataclass
class GoDeferStatement(GoStatement):
    """Defer statement: defer call()."""

    call: GoCallExpression = field(default_factory=lambda: GoCallExpression())


@dataclass
class GoGoStatement(GoStatement):
    """Go statement: go call()."""

    call: GoCallExpression = field(default_factory=lambda: GoCallExpression())


@dataclass
class GoCaseClause(GoNode):
    """Case clause in switch: case exprs: body or default: body."""

    cases: List[GoExpression] = field(default_factory=list)  # Empty for default
    body: List[GoStatement] = field(default_factory=list)


@dataclass
class GoSwitchStatement(GoStatement):
    """Switch statement: switch [init;] [tag] { cases }."""

    init: Optional[GoStatement] = None
    tag: Optional[GoExpression] = None
    cases: List[GoCaseClause] = field(default_factory=list)


# Expressions

@dataclass
class GoLiteral(GoExpression):
    """Literal value: string, int, float, rune, bool, nil."""

    value: Any = None
    raw: str = ""
    type_name: str = "string"


@dataclass
class GoIdentifier(GoExpression):
    """Variable or type identifier."""

    name: str = ""


@dataclass
class GoBinaryExpression(GoExpression):
    """Binary operation: left <op> right."""

    operator: str = "+"
    left: GoExpression = field(default_factory=GoExpression)
    right: GoExpression = field(default_factory=GoExpression)


@dataclass
class GoUnaryExpression(GoExpression):
    """Unary operation: <op> operand."""

    operator: str = "!"
    operand: GoExpression = field(default_factory=GoExpression)


@dataclass
class GoCallExpression(GoExpression):
    """Function or method call: callee(args)."""

    callee: GoExpression = field(default_factory=GoExpression)
    args: List[GoExpression] = field(default_factory=list)
    has_ellipsis: bool = False


@dataclass
class GoSelectorExpression(GoExpression):
    """Selector expression: expr.name (e.g. fmt.Println)."""

    expression: GoExpression = field(default_factory=GoExpression)
    name: str = ""


@dataclass
class GoIndexExpression(GoExpression):
    """Index access: expr[index]."""

    expression: GoExpression = field(default_factory=GoExpression)
    index: GoExpression = field(default_factory=GoExpression)


@dataclass
class GoSliceExpression(GoExpression):
    """Slice expression: expr[low:high[:max]]."""

    expression: GoExpression = field(default_factory=GoExpression)
    low: Optional[GoExpression] = None
    high: Optional[GoExpression] = None
    max: Optional[GoExpression] = None


@dataclass
class GoTypeAssertExpression(GoExpression):
    """Type assertion: expr.(Type)."""

    expression: GoExpression = field(default_factory=GoExpression)
    type_name: str = "any"


@dataclass
class GoCompositeLiteral(GoExpression):
    """Composite literal: Type{ elem1, elem2 } (e.g. []byte{1, 2}, []string{"a"})."""

    type_name: str = "[]byte"
    elements: List[GoExpression] = field(default_factory=list)


@dataclass
class GoKeyValueExpression(GoExpression):
    """Key-value pair in composite literal: key: value."""

    key: GoExpression = field(default_factory=GoExpression)
    value: GoExpression = field(default_factory=GoExpression)
