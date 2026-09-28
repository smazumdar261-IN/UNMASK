"""Java source code recursive-descent parser.

Per Section 14 of the Master Specification (Phase 8: Java):
Parses Java source code (.java) into a structured JavaCompilationUnit AST:
- Package, imports, classes, interfaces
- Fields, methods, parameters
- Statements: blocks, local variable declarations, if, while, for, return, expressions
- Expressions: literals, identifiers, binary/unary ops, method calls, field accesses, new, casts
"""

from __future__ import annotations

from typing import Any, List, Optional, Set

from core.exceptions import ParseError
from languages.java.ast_nodes import (
    JavaArrayAccess,
    JavaAssignmentExpression,
    JavaBinaryExpression,
    JavaBlock,
    JavaCastExpression,
    JavaClassDeclaration,
    JavaCompilationUnit,
    JavaExpression,
    JavaExpressionStatement,
    JavaFieldAccess,
    JavaFieldDeclaration,
    JavaIdentifier,
    JavaIfStatement,
    JavaImportDeclaration,
    JavaInterfaceDeclaration,
    JavaLiteral,
    JavaMethodCall,
    JavaMethodDeclaration,
    JavaNewArrayExpression,
    JavaNewClassExpression,
    JavaPackageDeclaration,
    JavaParameter,
    JavaReturnStatement,
    JavaStatement,
    JavaUnaryExpression,
    JavaVariableDeclarationStatement,
    JavaWhileStatement,
)
from languages.java.lexer import JavaLexer, JavaToken, JavaTokenType

PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6, "!=": 6,
    "<": 7, "<=": 7, ">": 7, ">=": 7, "instanceof": 7,
    "<<": 8, ">>": 8, ">>>": 8,
    "+": 9, "-": 9,
    "*": 10, "/": 10, "%": 10,
}

JAVA_MODIFIERS = {
    "public", "private", "protected", "static", "final", "abstract",
    "synchronized", "volatile", "transient", "native", "default"
}

PRIMITIVE_TYPES = {
    "void", "boolean", "byte", "short", "int", "long", "char", "float", "double", "var"
}


class JavaParser:
    """Parses Java tokens into Java AST nodes."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source = source
        self.filename = filename or "<java>"
        self.tokens: List[JavaToken] = JavaLexer(source, filename).tokenize()
        self.pos = 0

    def parse(self) -> JavaCompilationUnit:
        """Parse source into a JavaCompilationUnit root."""
        pkg = None
        imports: List[JavaImportDeclaration] = []
        types: List[Any] = []

        while not self._is_at_end():
            tok = self._current()

            # Package declaration: package com.foo.bar;
            if tok.value == "package":
                pkg = self._parse_package_declaration()
                continue

            # Import declaration: import [static] com.foo.Bar;
            if tok.value == "import":
                imports.append(self._parse_import_declaration())
                continue

            # Class or interface or empty semicolon
            if tok.value == ";":
                self._advance()
                continue

            # Parse type declaration (class, interface, enum, record)
            type_decl = self._parse_type_declaration()
            if type_decl:
                types.append(type_decl)

        return JavaCompilationUnit(package=pkg, imports=imports, types=types)

    def _current(self) -> JavaToken:
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> JavaToken:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _is_at_end(self) -> bool:
        return self._current().type == JavaTokenType.EOF

    def _advance(self) -> JavaToken:
        tok = self._current()
        if not self._is_at_end():
            self.pos += 1
        return tok

    def _match(self, value: str) -> bool:
        if self._current().value == value:
            self._advance()
            return True
        return False

    def _expect(self, value: str) -> JavaToken:
        tok = self._current()
        if tok.value != value:
            raise ParseError(
                message=f"Expected '{value}', found '{tok.value}'",
                filename=self.filename,
                lineno=tok.location.start_line,
                col_offset=tok.location.start_col,
            )
        return self._advance()

    def _consume_semicolon(self) -> None:
        if self._current().value == ";":
            self._advance()

    # --- Top-Level Parsers ---

    def _parse_package_declaration(self) -> JavaPackageDeclaration:
        pkg_tok = self._expect("package")
        name_parts: List[str] = []
        while not self._is_at_end() and self._current().value != ";":
            name_parts.append(self._advance().value)
        self._consume_semicolon()
        return JavaPackageDeclaration(name="".join(name_parts), location=pkg_tok.location)

    def _parse_import_declaration(self) -> JavaImportDeclaration:
        imp_tok = self._expect("import")
        is_static = bool(self._match("static"))
        name_parts: List[str] = []
        is_wildcard = False
        while not self._is_at_end() and self._current().value != ";":
            tok = self._advance()
            name_parts.append(tok.value)
            if tok.value == "*":
                is_wildcard = True
        self._consume_semicolon()
        return JavaImportDeclaration(
            name="".join(name_parts),
            is_static=is_static,
            is_wildcard=is_wildcard,
            location=imp_tok.location,
        )

    def _parse_type_declaration(self) -> Any:
        modifiers = self._parse_modifiers()
        tok = self._current()

        if tok.value in ("class", "record"):
            return self._parse_class_declaration(modifiers)
        elif tok.value == "interface":
            return self._parse_interface_declaration(modifiers)
        else:
            raise ParseError(
                message=f"Expected class or interface, found '{tok.value}'",
                filename=self.filename,
                lineno=tok.location.start_line,
                col_offset=tok.location.start_col,
            )

    def _parse_modifiers(self) -> List[str]:
        mods: List[str] = []
        while not self._is_at_end() and self._current().value in JAVA_MODIFIERS:
            mods.append(self._advance().value)
        return mods

    def _parse_type_name(self) -> str:
        """Parses a type identifier, including generics <T> and arrays []."""
        parts = [self._advance().value]
        # Generics <...>
        if self._match("<"):
            parts.append("<")
            depth = 1
            while not self._is_at_end() and depth > 0:
                tok = self._advance()
                if tok.value == "<":
                    depth += 1
                elif tok.value == ">":
                    depth -= 1
                parts.append(tok.value)
        # Array brackets []
        while self._current().value == "[" and self._peek().value == "]":
            self._advance()
            self._advance()
            parts.append("[]")
        return "".join(parts)

    def _parse_class_declaration(self, modifiers: List[str]) -> JavaClassDeclaration:
        cls_tok = self._advance()  # 'class'
        name_tok = self._advance()
        class_name = name_tok.value

        super_class = None
        if self._match("extends"):
            super_class = self._parse_type_name()

        interfaces: List[str] = []
        if self._match("implements"):
            while not self._is_at_end() and self._current().value != "{":
                interfaces.append(self._parse_type_name())
                self._match(",")

        self._expect("{")
        members: List[Any] = []
        while not self._is_at_end() and self._current().value != "}":
            member = self._parse_class_member()
            if member:
                members.append(member)
        self._expect("}")

        return JavaClassDeclaration(
            modifiers=modifiers,
            name=class_name,
            super_class=super_class,
            interfaces=interfaces,
            members=members,
            location=cls_tok.location,
        )

    def _parse_interface_declaration(self, modifiers: List[str]) -> JavaInterfaceDeclaration:
        if_tok = self._expect("interface")
        name_tok = self._advance()
        if_name = name_tok.value

        extends: List[str] = []
        if self._match("extends"):
            while not self._is_at_end() and self._current().value != "{":
                extends.append(self._parse_type_name())
                self._match(",")

        self._expect("{")
        members: List[Any] = []
        while not self._is_at_end() and self._current().value != "}":
            member = self._parse_class_member()
            if member:
                members.append(member)
        self._expect("}")

        return JavaInterfaceDeclaration(
            modifiers=modifiers,
            name=if_name,
            extends=extends,
            members=members,
            location=if_tok.location,
        )

    def _parse_class_member(self) -> Any:
        if self._current().value == ";":
            self._advance()
            return None

        modifiers = self._parse_modifiers()
        loc = self._current().location
        type_name = self._parse_type_name()
        name_tok = self._advance()
        name = name_tok.value

        # Method: name(params) { body } or name(params);
        if self._match("("):
            params = self._parse_parameters()
            self._expect(")")

            # Optional throws clause
            if self._match("throws"):
                while not self._is_at_end() and self._current().value not in ("{", ";"):
                    self._advance()

            body = None
            if self._current().value == "{":
                body = self._parse_block()
            else:
                self._consume_semicolon()

            return JavaMethodDeclaration(
                modifiers=modifiers,
                return_type=type_name,
                name=name,
                parameters=params,
                body=body,
                location=loc,
            )

        # Field: Type name [= init];
        init = None
        if self._match("="):
            init = self._parse_assignment_expression()
        self._consume_semicolon()

        return JavaFieldDeclaration(
            modifiers=modifiers,
            type_name=type_name,
            name=name,
            initializer=init,
            location=loc,
        )

    def _parse_parameters(self) -> List[JavaParameter]:
        params: List[JavaParameter] = []
        while not self._is_at_end() and self._current().value != ")":
            # skip optional 'final'
            self._match("final")
            ptype = self._parse_type_name()
            pname = self._advance().value
            params.append(JavaParameter(type_name=ptype, name=pname))
            if not self._match(","):
                break
        return params

    # --- Statement Parsers ---

    def _parse_block(self) -> JavaBlock:
        start_tok = self._expect("{")
        stmts: List[JavaStatement] = []
        while not self._is_at_end() and self._current().value != "}":
            stmt = self._parse_statement()
            if stmt:
                stmts.append(stmt)
        self._expect("}")
        return JavaBlock(statements=stmts, location=start_tok.location)

    def _parse_statement(self) -> JavaStatement:
        tok = self._current()

        if tok.value == ";":
            self._advance()
            return JavaBlock(statements=[], location=tok.location)

        if tok.value == "{":
            return self._parse_block()

        if tok.value == "if":
            return self._parse_if_statement()

        if tok.value == "while":
            return self._parse_while_statement()

        if tok.value == "return":
            return self._parse_return_statement()

        # Local variable declaration or Expression statement
        if self._is_type_at_current():
            return self._parse_variable_declaration_statement()

        # Expression statement
        expr = self._parse_expression()
        self._consume_semicolon()
        return JavaExpressionStatement(expression=expr, location=expr.location)

    def _is_type_at_current(self) -> bool:
        """Determines if the current position starts a local variable declaration."""
        tok = self._current()
        if tok.value in PRIMITIVE_TYPES or tok.value == "final":
            return True

        # Check if IDENTIFIER followed by IDENTIFIER (e.g. String s = ...)
        if tok.type == JavaTokenType.IDENTIFIER:
            # Look ahead for generics or array brackets followed by identifier
            offset = 1
            if self._peek(offset).value == "<":
                depth = 1
                offset += 1
                while depth > 0 and self.pos + offset < len(self.tokens):
                    v = self._peek(offset).value
                    if v == "<":
                        depth += 1
                    elif v == ">":
                        depth -= 1
                    offset += 1
            while self._peek(offset).value == "[" and self._peek(offset + 1).value == "]":
                offset += 2
            next_tok = self._peek(offset)
            return next_tok.type == JavaTokenType.IDENTIFIER and next_tok.value not in (
                "(", ".", "=", "+=", "-=", "*=", "/="
            )
        return False

    def _parse_variable_declaration_statement(self) -> JavaVariableDeclarationStatement:
        is_final = bool(self._match("final"))
        type_name = self._parse_type_name()
        name_tok = self._advance()
        init = None
        if self._match("="):
            init = self._parse_assignment_expression()
        self._consume_semicolon()
        return JavaVariableDeclarationStatement(
            type_name=type_name,
            name=name_tok.value,
            initializer=init,
            is_final=is_final,
            location=name_tok.location,
        )

    def _parse_if_statement(self) -> JavaIfStatement:
        if_tok = self._expect("if")
        self._expect("(")
        cond = self._parse_expression()
        self._expect(")")
        then_branch = self._parse_statement()
        else_branch = None
        if self._match("else"):
            else_branch = self._parse_statement()
        return JavaIfStatement(
            condition=cond,
            then_branch=then_branch,
            else_branch=else_branch,
            location=if_tok.location,
        )

    def _parse_while_statement(self) -> JavaWhileStatement:
        while_tok = self._expect("while")
        self._expect("(")
        cond = self._parse_expression()
        self._expect(")")
        body = self._parse_statement()
        return JavaWhileStatement(condition=cond, body=body, location=while_tok.location)

    def _parse_return_statement(self) -> JavaReturnStatement:
        ret_tok = self._expect("return")
        expr = None
        if self._current().value != ";":
            expr = self._parse_expression()
        self._consume_semicolon()
        return JavaReturnStatement(expression=expr, location=ret_tok.location)

    # --- Expression Parsers ---

    def _parse_expression(self) -> JavaExpression:
        return self._parse_assignment_expression()

    def _parse_assignment_expression(self) -> JavaExpression:
        left = self._parse_binary_expression(min_prec=1)
        if self._current().value in ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^="):
            op_tok = self._advance()
            val = self._parse_assignment_expression()
            return JavaAssignmentExpression(target=left, operator=op_tok.value, value=val, location=left.location)
        return left

    def _parse_binary_expression(self, min_prec: int) -> JavaExpression:
        left = self._parse_unary_expression()

        while True:
            tok = self._current()
            if tok.type != JavaTokenType.PUNCTUATOR and tok.value != "instanceof":
                break
            op = tok.value
            prec = PRECEDENCE.get(op, 0)
            if prec < min_prec:
                break
            self._advance()
            right = self._parse_binary_expression(min_prec=prec + 1)
            left = JavaBinaryExpression(operator=op, left=left, right=right, location=left.location)

        return left

    def _parse_unary_expression(self) -> JavaExpression:
        tok = self._current()
        if tok.type == JavaTokenType.PUNCTUATOR and tok.value in ("!", "-", "+", "~", "++", "--"):
            self._advance()
            operand = self._parse_unary_expression()
            return JavaUnaryExpression(operator=tok.value, operand=operand, is_prefix=True, location=tok.location)

        # Cast expression: (Type) expr
        if tok.value == "(" and self._is_cast():
            self._advance()  # consume '('
            cast_type = self._parse_type_name()
            self._expect(")")
            expr = self._parse_unary_expression()
            return JavaCastExpression(type_name=cast_type, expression=expr, location=tok.location)

        return self._parse_postfix_and_call_expression()

    def _is_cast(self) -> bool:
        """Heuristic to check if '(' starts a cast."""
        next_tok = self._peek(1)
        if next_tok.value in PRIMITIVE_TYPES:
            return True
        if next_tok.type == JavaTokenType.IDENTIFIER and self._peek(2).value == ")":
            # (String) expr
            return True
        return False

    def _parse_postfix_and_call_expression(self) -> JavaExpression:
        expr = self._parse_primary()

        while True:
            tok = self._current()

            # Method call or Field access: expr.name or expr.name(args)
            if self._match("."):
                name_tok = self._advance()
                name = name_tok.value
                if self._match("("):
                    args = self._parse_arguments()
                    self._expect(")")
                    expr = JavaMethodCall(target=expr, name=name, arguments=args, location=expr.location)
                else:
                    expr = JavaFieldAccess(target=expr, name=name, location=expr.location)

            # Array access: expr[index]
            elif self._match("["):
                idx = self._parse_expression()
                self._expect("]")
                expr = JavaArrayAccess(target=expr, index=idx, location=expr.location)

            # Direct method call on unqualified identifier: name(args)
            elif isinstance(expr, JavaIdentifier) and self._match("("):
                args = self._parse_arguments()
                self._expect(")")
                expr = JavaMethodCall(target=None, name=expr.name, arguments=args, location=expr.location)

            # Postfix ++ or --
            elif tok.value in ("++", "--"):
                self._advance()
                expr = JavaUnaryExpression(operator=tok.value, operand=expr, is_prefix=False, location=expr.location)
            else:
                break

        return expr

    def _parse_arguments(self) -> List[JavaExpression]:
        args: List[JavaExpression] = []
        while not self._is_at_end() and self._current().value != ")":
            args.append(self._parse_assignment_expression())
            if not self._match(","):
                break
        return args

    def _parse_primary(self) -> JavaExpression:
        tok = self._current()

        # String literal
        if tok.type == JavaTokenType.STRING:
            self._advance()
            return JavaLiteral(value=tok.value, raw=repr(tok.value), type_name="String", location=tok.location)

        # Character literal
        if tok.type == JavaTokenType.CHAR:
            self._advance()
            return JavaLiteral(value=tok.value, raw=repr(tok.value), type_name="char", location=tok.location)

        # Number literal
        if tok.type == JavaTokenType.NUMBER:
            self._advance()
            val: Any = None
            tname = "int"
            raw = tok.value
            clean = raw[:-1] if (raw.endswith(("l", "L")) or (raw.endswith(("f", "F", "d", "D")) and not raw.lower().startswith("0x"))) else raw
            try:
                if raw.endswith(("l", "L")):
                    tname = "long"
                    val = int(clean, 0)
                elif raw.endswith(("f", "F")) and not raw.lower().startswith("0x"):
                    tname = "float"
                    val = float(clean)
                elif (raw.endswith(("d", "D")) and not raw.lower().startswith("0x")) or "." in raw:
                    tname = "double"
                    val = float(clean)
                else:
                    val = int(clean, 0)
            except ValueError:
                val = raw
            return JavaLiteral(value=val, raw=raw, type_name=tname, location=tok.location)

        # Boolean and null
        if tok.value == "true":
            self._advance()
            return JavaLiteral(value=True, raw="true", type_name="boolean", location=tok.location)
        if tok.value == "false":
            self._advance()
            return JavaLiteral(value=False, raw="false", type_name="boolean", location=tok.location)
        if tok.value == "null":
            self._advance()
            return JavaLiteral(value=None, raw="null", type_name="null", location=tok.location)

        # Parenthesized expression
        if tok.value == "(":
            self._advance()
            expr = self._parse_expression()
            self._expect(")")
            return expr

        # Object or Array creation: new Type(...) or new Type[...]
        if tok.value == "new":
            return self._parse_new_expression()

        # Identifier
        if tok.type == JavaTokenType.IDENTIFIER or tok.value in ("this", "super"):
            self._advance()
            return JavaIdentifier(name=tok.value, location=tok.location)

        raise ParseError(
            message=f"Unexpected token in Java expression: '{tok.value}'",
            filename=self.filename,
            lineno=tok.location.start_line,
            col_offset=tok.location.start_col,
        )

    def _parse_new_expression(self) -> JavaExpression:
        new_tok = self._expect("new")
        type_name = self._parse_type_name()

        # Array creation: new byte[] { ... } or new int[10]
        if type_name.endswith("[]") or self._match("["):
            dims = []
            if not type_name.endswith("[]"):
                if self._current().value != "]":
                    dims.append(self._parse_expression())
                self._expect("]")
            else:
                type_name = type_name[:-2]

            inits = []
            if self._match("{"):
                while not self._is_at_end() and self._current().value != "}":
                    inits.append(self._parse_assignment_expression())
                    if not self._match(","):
                        break
                self._expect("}")

            return JavaNewArrayExpression(
                type_name=type_name,
                dimensions=dims,
                initializers=inits,
                location=new_tok.location,
            )

        # Object creation: new Type(args)
        self._expect("(")
        args = self._parse_arguments()
        self._expect(")")
        return JavaNewClassExpression(type_name=type_name, arguments=args, location=new_tok.location)
