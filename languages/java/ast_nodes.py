"""Java AST node definitions.

Per Section 14 and Section 16 of the Master Specification (Phase 8: Java):
Represents Java source and decompiled bytecode constructs:
- Compilation units, packages, imports
- Class and interface declarations, fields, methods, parameters
- Statements (blocks, variable declarations, if, while, for, return, expr)
- Expressions (literals, identifiers, binary/unary ops, method calls, field access, new, casts)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.provenance import SourceLocation


@dataclass
class JavaNode:
    """Base class for all Java AST nodes."""

    location: SourceLocation = field(default_factory=SourceLocation)


@dataclass
class JavaPackageDeclaration(JavaNode):
    """Package statement: package com.example.app;."""

    name: str = ""


@dataclass
class JavaImportDeclaration(JavaNode):
    """Import statement: import [static] pkg.Name[*];."""

    name: str = ""
    is_static: bool = False
    is_wildcard: bool = False


@dataclass
class JavaParameter(JavaNode):
    """Method parameter: Type name."""

    type_name: str = "Object"
    name: str = ""


@dataclass
class JavaStatement(JavaNode):
    """Base class for Java statements."""


@dataclass
class JavaExpression(JavaNode):
    """Base class for Java expressions."""


@dataclass
class JavaBlock(JavaStatement):
    """Block of statements enclosed in braces: { ... }."""

    statements: List[JavaStatement] = field(default_factory=list)


@dataclass
class JavaFieldDeclaration(JavaNode):
    """Class field: [modifiers] Type name [= init];."""

    modifiers: List[str] = field(default_factory=list)
    type_name: str = "Object"
    name: str = ""
    initializer: Optional[JavaExpression] = None


@dataclass
class JavaMethodDeclaration(JavaNode):
    """Method declaration: [modifiers] ReturnType name(params) { body }."""

    modifiers: List[str] = field(default_factory=list)
    return_type: str = "void"
    name: str = ""
    parameters: List[JavaParameter] = field(default_factory=list)
    body: Optional[JavaBlock] = None


@dataclass
class JavaClassDeclaration(JavaNode):
    """Class declaration: [modifiers] class Name [extends Super] [implements Interfaces] { ... }."""

    modifiers: List[str] = field(default_factory=list)
    name: str = ""
    super_class: Optional[str] = None
    interfaces: List[str] = field(default_factory=list)
    members: List[Any] = field(default_factory=list)  # JavaFieldDeclaration, JavaMethodDeclaration


@dataclass
class JavaInterfaceDeclaration(JavaNode):
    """Interface declaration: [modifiers] interface Name [extends Interfaces] { ... }."""

    modifiers: List[str] = field(default_factory=list)
    name: str = ""
    extends: List[str] = field(default_factory=list)
    members: List[Any] = field(default_factory=list)


@dataclass
class JavaCompilationUnit(JavaNode):
    """Root compilation unit for a Java source or decompiled class file."""

    package: Optional[JavaPackageDeclaration] = None
    imports: List[JavaImportDeclaration] = field(default_factory=list)
    types: List[Any] = field(default_factory=list)  # JavaClassDeclaration, JavaInterfaceDeclaration


# Statements

@dataclass
class JavaExpressionStatement(JavaStatement):
    """Statement consisting of an expression: expr;."""

    expression: JavaExpression = field(default_factory=JavaExpression)


@dataclass
class JavaVariableDeclarationStatement(JavaStatement):
    """Local variable declaration: [final] Type name [= init];."""

    type_name: str = "Object"
    name: str = ""
    initializer: Optional[JavaExpression] = None
    is_final: bool = False


@dataclass
class JavaIfStatement(JavaStatement):
    """Conditional statement: if (condition) then_branch [else else_branch]."""

    condition: JavaExpression = field(default_factory=JavaExpression)
    then_branch: JavaStatement = field(default_factory=JavaStatement)
    else_branch: Optional[JavaStatement] = None


@dataclass
class JavaWhileStatement(JavaStatement):
    """While loop: while (condition) body."""

    condition: JavaExpression = field(default_factory=JavaExpression)
    body: JavaStatement = field(default_factory=JavaStatement)


@dataclass
class JavaForStatement(JavaStatement):
    """For loop: for (init; condition; update) body."""

    init: Optional[Any] = None  # JavaVariableDeclarationStatement or JavaExpressionStatement
    condition: Optional[JavaExpression] = None
    update: Optional[JavaExpression] = None
    body: JavaStatement = field(default_factory=JavaStatement)


@dataclass
class JavaReturnStatement(JavaStatement):
    """Return statement: return [expr];."""

    expression: Optional[JavaExpression] = None


# Expressions

@dataclass
class JavaLiteral(JavaExpression):
    """Literal constant: 123, "hello", true, null."""

    value: Any = None
    raw: str = ""
    type_name: str = "Object"


@dataclass
class JavaIdentifier(JavaExpression):
    """Variable or symbol identifier."""

    name: str = ""


@dataclass
class JavaBinaryExpression(JavaExpression):
    """Binary operation: left <op> right."""

    operator: str = "+"
    left: JavaExpression = field(default_factory=JavaExpression)
    right: JavaExpression = field(default_factory=JavaExpression)


@dataclass
class JavaUnaryExpression(JavaExpression):
    """Unary operation: <op> operand."""

    operator: str = "!"
    operand: JavaExpression = field(default_factory=JavaExpression)
    is_prefix: bool = True


@dataclass
class JavaMethodCall(JavaExpression):
    """Method invocation: [target.]methodName(args)."""

    target: Optional[JavaExpression] = None
    name: str = ""
    arguments: List[JavaExpression] = field(default_factory=list)


@dataclass
class JavaFieldAccess(JavaExpression):
    """Field access: target.fieldName."""

    target: JavaExpression = field(default_factory=JavaExpression)
    name: str = ""


@dataclass
class JavaNewClassExpression(JavaExpression):
    """Object allocation: new Type(args)."""

    type_name: str = "Object"
    arguments: List[JavaExpression] = field(default_factory=list)


@dataclass
class JavaNewArrayExpression(JavaExpression):
    """Array allocation: new Type[dim] or new Type[] { val1, val2 }."""

    type_name: str = "int"
    dimensions: List[JavaExpression] = field(default_factory=list)
    initializers: List[JavaExpression] = field(default_factory=list)


@dataclass
class JavaArrayAccess(JavaExpression):
    """Array indexing: array[index]."""

    target: JavaExpression = field(default_factory=JavaExpression)
    index: JavaExpression = field(default_factory=JavaExpression)


@dataclass
class JavaAssignmentExpression(JavaExpression):
    """Assignment: target = value."""

    target: JavaExpression = field(default_factory=JavaExpression)
    operator: str = "="
    value: JavaExpression = field(default_factory=JavaExpression)


@dataclass
class JavaCastExpression(JavaExpression):
    """Type cast: (Type) expr."""

    type_name: str = "Object"
    expression: JavaExpression = field(default_factory=JavaExpression)
