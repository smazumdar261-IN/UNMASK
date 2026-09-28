"""Recursive-descent TypeScript parser.

Per Section 13 of the Master Specification (Phase 7: TypeScript):
Parses TypeScript source into an AST preserving:
- Interfaces (interface Foo { ... })
- Type aliases (type Bar = string | number)
- Enums (enum Status { ... })
- Generics (<T, U>)
- Decorators (@decorator)
- Type annotations on variables, parameters, and function return types
- Type assertions (expr as Type)
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.exceptions import ParseError
from languages.javascript.ast_nodes import (
    JSBlockStatement,
    JSCallExpression,
    JSExpression,
    JSExpressionStatement,
    JSFunctionDeclaration,
    JSIdentifier,
    JSNode,
    JSStatement,
    JSVariableDeclaration,
    JSVariableDeclarator,
)
from languages.javascript.lexer import JSTokenType
from languages.javascript.parser import JSParser, PRECEDENCE
from languages.typescript.ast_nodes import (
    TSAsExpression,
    TSDecorator,
    TSEnumDeclaration,
    TSEnumMember,
    TSInterfaceDeclaration,
    TSMethodSignature,
    TSParameter,
    TSPropertySignature,
    TSTypeAliasDeclaration,
    TSTypeAnnotation,
    TSTypeParameter,
    TSTypeParameterDeclaration,
)
from languages.typescript.lexer import TSLexer


class TSParser(JSParser):
    """Parses TypeScript tokens into AST nodes preserving TypeScript constructs."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source = source
        self.filename = filename or "<typescript>"
        self.tokens = TSLexer(source, filename).tokenize()
        self.pos = 0

    def _parse_statement(self) -> JSStatement:
        # Check for decorators before declaration: @decorator
        decorators: List[TSDecorator] = []
        while self._current().value == "@":
            decorators.append(self._parse_decorator())

        tok = self._current()

        # Interface declaration: interface Name<T> { ... }
        if tok.value == "interface":
            return self._parse_interface_declaration()

        # Type alias declaration: type Name<T> = Type;
        if tok.value == "type":
            return self._parse_type_alias_declaration()

        # Const enum or standard enum: [const] enum Name { ... }
        if tok.value == "const" and self._peek().value == "enum":
            self._advance()  # consume 'const'
            return self._parse_enum_declaration(is_const=True)

        if tok.value == "enum":
            return self._parse_enum_declaration(is_const=False)

        # Ambient declarations: declare var/let/const/function/etc.
        if tok.value == "declare":
            self._advance()

        # Function declaration with potential decorators and types
        if tok.value == "function":
            return self._parse_function_declaration(decorators=decorators)

        # Variable declaration
        if tok.value in ("var", "let", "const"):
            return self._parse_variable_declaration()

        # Delegate to standard JS statement parsing
        stmt = super()._parse_statement()
        if decorators and isinstance(stmt, JSFunctionDeclaration):
            stmt.decorators = decorators
        return stmt

    def _parse_decorator(self) -> TSDecorator:
        at_tok = self._expect("@")
        expr = self._parse_call_and_member_expression()
        return TSDecorator(expression=expr, location=at_tok.location)

    def _parse_interface_declaration(self) -> TSInterfaceDeclaration:
        if_tok = self._expect("interface")
        id_tok = self._advance()
        interface_id = JSIdentifier(name=id_tok.value, location=id_tok.location)

        type_params = None
        if self._match("<"):
            type_params = self._parse_type_parameters()

        extends_list: List[Any] = []
        if self._match("extends"):
            while not self._is_at_end() and self._current().value != "{":
                base_tok = self._advance()
                extends_list.append(JSIdentifier(name=base_tok.value, location=base_tok.location))
                self._match(",")

        self._expect("{")
        body: List[Any] = []
        while not self._is_at_end() and self._current().value != "}":
            is_readonly = bool(self._match("readonly"))
            key_tok = self._advance()
            key_id = JSIdentifier(name=key_tok.value, location=key_tok.location)
            is_optional = bool(self._match("?"))

            # Method signature: method(params): ReturnType;
            if self._match("("):
                params = self._parse_typed_parameters()
                ret_type = None
                if self._match(":"):
                    ret_type = self._parse_type_annotation(stop_at_brace=True)
                self._consume_semicolon()
                body.append(
                    TSMethodSignature(
                        key=key_id,
                        params=params,
                        return_type=ret_type,
                        location=key_tok.location,
                    )
                )
            else:
                # Property signature: prop: Type;
                type_ann = None
                if self._match(":"):
                    type_ann = self._parse_type_annotation(stop_at_brace=True)
                self._consume_semicolon()
                body.append(
                    TSPropertySignature(
                        key=key_id,
                        type_annotation=type_ann,
                        optional=is_optional,
                        readonly=is_readonly,
                        location=key_tok.location,
                    )
                )

        self._expect("}")
        return TSInterfaceDeclaration(
            id=interface_id,
            type_parameters=type_params,
            extends=extends_list,
            body=body,
            location=if_tok.location,
        )

    def _parse_type_alias_declaration(self) -> TSTypeAliasDeclaration:
        type_tok = self._expect("type")
        id_tok = self._advance()
        alias_id = JSIdentifier(name=id_tok.value, location=id_tok.location)

        type_params = None
        if self._match("<"):
            type_params = self._parse_type_parameters()

        self._expect("=")
        type_ann = self._parse_type_annotation()
        self._consume_semicolon()
        return TSTypeAliasDeclaration(
            id=alias_id,
            type_parameters=type_params,
            type_annotation=type_ann,
            location=type_tok.location,
        )

    def _parse_enum_declaration(self, is_const: bool = False) -> TSEnumDeclaration:
        enum_tok = self._expect("enum")
        id_tok = self._advance()
        enum_id = JSIdentifier(name=id_tok.value, location=id_tok.location)

        self._expect("{")
        members: List[TSEnumMember] = []
        while not self._is_at_end() and self._current().value != "}":
            mem_tok = self._advance()
            mem_id = JSIdentifier(name=mem_tok.value, location=mem_tok.location)
            init_expr = None
            if self._match("="):
                init_expr = self._parse_assignment_expression()
            members.append(TSEnumMember(id=mem_id, initializer=init_expr, location=mem_tok.location))
            self._match(",")
        self._expect("}")
        return TSEnumDeclaration(
            id=enum_id,
            members=members,
            is_const=is_const,
            location=enum_tok.location,
        )

    def _parse_variable_declaration(self) -> JSVariableDeclaration:
        kind_tok = self._advance()  # var, let, const
        declarations: List[JSVariableDeclarator] = []

        while True:
            id_tok = self._current()
            if id_tok.type not in (JSTokenType.IDENTIFIER, JSTokenType.KEYWORD):
                raise ParseError(
                    message=f"Expected variable name, found '{id_tok.value}'",
                    filename=self.filename,
                    lineno=id_tok.location.start_line,
                    col_offset=id_tok.location.start_col,
                )
            self._advance()
            var_id = JSIdentifier(name=id_tok.value, location=id_tok.location)

            type_ann = None
            if self._match(":"):
                type_ann = self._parse_type_annotation()

            init_expr = None
            if self._match("="):
                init_expr = self._parse_assignment_expression()

            declarations.append(
                JSVariableDeclarator(
                    id=var_id,
                    init=init_expr,
                    type_annotation=type_ann,
                    location=id_tok.location,
                )
            )
            if not self._match(","):
                break

        self._consume_semicolon()
        return JSVariableDeclaration(kind=kind_tok.value, declarations=declarations, location=kind_tok.location)

    def _parse_function_declaration(
        self, decorators: Optional[List[TSDecorator]] = None
    ) -> JSFunctionDeclaration:
        fn_tok = self._expect("function")
        fn_name = None
        if self._current().type in (JSTokenType.IDENTIFIER, JSTokenType.KEYWORD) and self._current().value not in ("(", "<"):
            id_tok = self._advance()
            fn_name = JSIdentifier(name=id_tok.value, location=id_tok.location)

        type_params = None
        if self._match("<"):
            type_params = self._parse_type_parameters()

        self._expect("(")
        params = self._parse_typed_parameters()

        ret_type = None
        if self._match(":"):
            ret_type = self._parse_type_annotation(stop_at_brace=True)

        body = self._parse_block()
        return JSFunctionDeclaration(
            id=fn_name,
            params=params,
            body=body,
            return_type=ret_type,
            type_parameters=type_params,
            decorators=decorators or [],
            location=fn_tok.location,
        )

    def _parse_typed_parameters(self) -> List[Any]:
        params: List[Any] = []
        while not self._is_at_end() and self._current().value != ")":
            p_tok = self._advance()
            p_id = JSIdentifier(name=p_tok.value, location=p_tok.location)
            is_optional = bool(self._match("?"))
            p_type = None
            if self._match(":"):
                p_type = self._parse_type_annotation()
            p_default = None
            if self._match("="):
                p_default = self._parse_assignment_expression()

            params.append(
                TSParameter(
                    id=p_id,
                    type_annotation=p_type,
                    optional=is_optional,
                    default=p_default,
                    location=p_tok.location,
                )
            )
            if not self._match(","):
                break
        self._expect(")")
        return params

    def _parse_type_parameters(self) -> TSTypeParameterDeclaration:
        start_tok = self._current()
        params: List[TSTypeParameter] = []
        while not self._is_at_end() and self._current().value != ">":
            p_tok = self._advance()
            constraint = None
            if self._match("extends"):
                constraint = self._parse_type_annotation()
            default = None
            if self._match("="):
                default = self._parse_type_annotation()
            params.append(
                TSTypeParameter(
                    name=p_tok.value,
                    constraint=constraint,
                    default=default,
                    location=p_tok.location,
                )
            )
            if not self._match(","):
                break
        self._expect(">")
        return TSTypeParameterDeclaration(params=params, location=start_tok.location)

    def _parse_type_annotation(self, stop_at_brace: bool = False) -> TSTypeAnnotation:
        """Parses TypeScript type annotation tokens until an outer delimiter."""
        start_tok = self._current()
        raw_parts: List[str] = []
        depth_paren = 0
        depth_brace = 0
        depth_bracket = 0
        depth_angle = 0

        while not self._is_at_end():
            tok = self._current()
            val = tok.value

            if depth_paren == 0 and depth_brace == 0 and depth_bracket == 0 and depth_angle == 0:
                if val in (";", ",", "=") or (stop_at_brace and val in ("{", "}")):
                    break

            if val == "(":
                depth_paren += 1
            elif val == ")":
                if depth_paren == 0:
                    break
                depth_paren -= 1
            elif val == "{":
                depth_brace += 1
            elif val == "}":
                if depth_brace == 0:
                    break
                depth_brace -= 1
            elif val == "[":
                depth_bracket += 1
            elif val == "]":
                if depth_bracket == 0:
                    break
                depth_bracket -= 1
            elif val == "<":
                depth_angle += 1
            elif val == ">":
                if depth_angle == 0:
                    break
                depth_angle -= 1

            raw_parts.append(val)
            self._advance()

        if not raw_parts:
            raise ParseError("Expected type annotation", location=start_tok.location)

        raw_str = (
            " ".join(raw_parts)
            .replace(" . ", ".")
            .replace(" : ", ": ")
            .replace(" < ", "<")
            .replace(" > ", ">")
            .replace(" [ ]", "[]")
            .replace("< ", "<")
            .replace(" >", ">")
        )
        base_name = raw_parts[0] if raw_parts else ""
        return TSTypeAnnotation(
            raw=raw_str,
            type_name=base_name,
            location=start_tok.location,
        )

    def _parse_binary_expression(self, min_prec: int) -> JSExpression:
        left = self._parse_unary_expression()

        while True:
            tok = self._current()

            # Type assertion: expr as Type
            if tok.value == "as":
                self._advance()
                type_ann = self._parse_type_annotation()
                left = TSAsExpression(expression=left, type_annotation=type_ann, location=left.location)
                continue

            if tok.type != JSTokenType.PUNCTUATOR:
                break
            op = tok.value
            prec = PRECEDENCE.get(op, 0)
            if prec < min_prec:
                break
            self._advance()
            right = self._parse_binary_expression(min_prec=prec + 1)
            from languages.javascript.ast_nodes import JSBinaryExpression
            left = JSBinaryExpression(operator=op, left=left, right=right, location=left.location)

        return left
