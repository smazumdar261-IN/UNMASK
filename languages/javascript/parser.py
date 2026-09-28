"""Recursive-descent JavaScript (ECMAScript) AST parser.

Per Section 12 of the Master Specification:
Parses JavaScript source into an ESTree-compatible AST with line/column tracking.
Handles:
- Statements: var, let, const, function, return, if, while, for, block, expr
- Expressions: calls, member access (dot and computed bracket), binary, unary,
  ternary conditional, assignments, sequences, object literals, array literals
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.exceptions import ParseError
from languages.javascript.ast_nodes import (
    JSArrayExpression,
    JSAssignmentExpression,
    JSBinaryExpression,
    JSBlockStatement,
    JSBreakStatement,
    JSCallExpression,
    JSConditionalExpression,
    JSContinueStatement,
    JSEmptyStatement,
    JSExpression,
    JSExpressionStatement,
    JSForStatement,
    JSFunctionDeclaration,
    JSFunctionExpression,
    JSIdentifier,
    JSIfStatement,
    JSLiteral,
    JSMemberExpression,
    JSNode,
    JSObjectExpression,
    JSProgram,
    JSProperty,
    JSReturnStatement,
    JSSequenceExpression,
    JSStatement,
    JSUnaryExpression,
    JSVariableDeclaration,
    JSVariableDeclarator,
    JSWhileStatement,
)
from languages.javascript.lexer import JSLexer, JSToken, JSTokenType


# Binary operator precedence (higher = tighter binding)
PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6, "!=": 6, "===": 6, "!==": 6,
    "<": 7, "<=": 7, ">": 7, ">=": 7,
    "<<": 8, ">>": 8, ">>>": 8,
    "+": 9, "-": 9,
    "*": 10, "/": 10, "%": 10,
}


class JSParser:
    """Parses JavaScript tokens into ESTree AST nodes."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.source = source
        self.filename = filename or "<javascript>"
        self.tokens: List[JSToken] = JSLexer(source, filename).tokenize()
        self.pos: int = 0

    def parse(self) -> JSProgram:
        """Parse source into a JSProgram root node."""
        body: List[JSStatement] = []
        while not self._is_at_end():
            stmt = self._parse_statement()
            if stmt:
                body.append(stmt)
        return JSProgram(body=body)

    def _current(self) -> JSToken:
        return self.tokens[self.pos]

    def _peek(self, offset: int = 1) -> JSToken:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _is_at_end(self) -> bool:
        return self._current().type == JSTokenType.EOF

    def _advance(self) -> JSToken:
        tok = self._current()
        if not self._is_at_end():
            self.pos += 1
        return tok

    def _match(self, value: str) -> bool:
        if self._current().value == value:
            self._advance()
            return True
        return False

    def _expect(self, value: str) -> JSToken:
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

    # --- Statement Parsers ---

    def _parse_statement(self) -> JSStatement:
        tok = self._current()

        if tok.value == ";":
            self._advance()
            return JSEmptyStatement(location=tok.location)

        if tok.value == "{":
            return self._parse_block()

        if tok.value in ("var", "let", "const"):
            return self._parse_variable_declaration()

        if tok.value == "function":
            return self._parse_function_declaration()

        if tok.value == "return":
            return self._parse_return_statement()

        if tok.value == "if":
            return self._parse_if_statement()

        if tok.value == "while":
            return self._parse_while_statement()

        if tok.value == "for":
            return self._parse_for_statement()

        if tok.value == "break":
            self._advance()
            self._consume_semicolon()
            return JSBreakStatement(location=tok.location)

        if tok.value == "continue":
            self._advance()
            self._consume_semicolon()
            return JSContinueStatement(location=tok.location)

        # Expression statement
        expr = self._parse_expression()
        self._consume_semicolon()
        return JSExpressionStatement(expression=expr, location=expr.location)

    def _parse_block(self) -> JSBlockStatement:
        start_tok = self._expect("{")
        body: List[JSStatement] = []
        while not self._is_at_end() and self._current().value != "}":
            body.append(self._parse_statement())
        self._expect("}")
        return JSBlockStatement(body=body, location=start_tok.location)

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
            init_expr = None
            if self._match("="):
                init_expr = self._parse_assignment_expression()

            declarations.append(JSVariableDeclarator(id=var_id, init=init_expr, location=id_tok.location))
            if not self._match(","):
                break

        self._consume_semicolon()
        return JSVariableDeclaration(kind=kind_tok.value, declarations=declarations, location=kind_tok.location)

    def _parse_function_declaration(self) -> JSFunctionDeclaration:
        fn_tok = self._expect("function")
        fn_name = None
        if self._current().type == JSTokenType.IDENTIFIER:
            id_tok = self._advance()
            fn_name = JSIdentifier(name=id_tok.value, location=id_tok.location)

        self._expect("(")
        params: List[JSIdentifier] = []
        while not self._is_at_end() and self._current().value != ")":
            p_tok = self._advance()
            params.append(JSIdentifier(name=p_tok.value, location=p_tok.location))
            if not self._match(","):
                break
        self._expect(")")

        body = self._parse_block()
        return JSFunctionDeclaration(id=fn_name, params=params, body=body, location=fn_tok.location)

    def _parse_return_statement(self) -> JSReturnStatement:
        ret_tok = self._expect("return")
        arg = None
        if self._current().value != ";" and not self._is_at_end() and self._current().value != "}":
            arg = self._parse_expression()
        self._consume_semicolon()
        return JSReturnStatement(argument=arg, location=ret_tok.location)

    def _parse_if_statement(self) -> JSIfStatement:
        if_tok = self._expect("if")
        self._expect("(")
        test = self._parse_expression()
        self._expect(")")
        consequent = self._parse_statement()
        alternate = None
        if self._match("else"):
            alternate = self._parse_statement()
        return JSIfStatement(test=test, consequent=consequent, alternate=alternate, location=if_tok.location)

    def _parse_while_statement(self) -> JSWhileStatement:
        while_tok = self._expect("while")
        self._expect("(")
        test = self._parse_expression()
        self._expect(")")
        body = self._parse_statement()
        return JSWhileStatement(test=test, body=body, location=while_tok.location)

    def _parse_for_statement(self) -> JSForStatement:
        for_tok = self._expect("for")
        self._expect("(")
        init = None
        if self._current().value != ";":
            if self._current().value in ("var", "let", "const"):
                init = self._parse_variable_declaration()
            else:
                init = self._parse_expression()
                self._consume_semicolon()
        else:
            self._advance()

        test = None
        if self._current().value != ";":
            test = self._parse_expression()
        self._consume_semicolon()

        update = None
        if self._current().value != ")":
            update = self._parse_expression()
        self._expect(")")

        body = self._parse_statement()
        return JSForStatement(init=init, test=test, update=update, body=body, location=for_tok.location)

    # --- Expression Parsers ---

    def _parse_expression(self) -> JSExpression:
        expr = self._parse_assignment_expression()
        if self._current().value == ",":
            exprs = [expr]
            while self._match(","):
                exprs.append(self._parse_assignment_expression())
            return JSSequenceExpression(expressions=exprs, location=expr.location)
        return expr

    def _parse_assignment_expression(self) -> JSExpression:
        left = self._parse_conditional_expression()
        if self._current().value in ("=", "+=", "-=", "*=", "/=", "%=", "^=", "&=", "|="):
            op_tok = self._advance()
            right = self._parse_assignment_expression()
            return JSAssignmentExpression(operator=op_tok.value, left=left, right=right, location=left.location)
        return left

    def _parse_conditional_expression(self) -> JSExpression:
        test = self._parse_binary_expression(min_prec=1)
        if self._match("?"):
            consequent = self._parse_assignment_expression()
            self._expect(":")
            alternate = self._parse_assignment_expression()
            return JSConditionalExpression(
                test=test, consequent=consequent, alternate=alternate, location=test.location
            )
        return test

    def _parse_binary_expression(self, min_prec: int) -> JSExpression:
        left = self._parse_unary_expression()

        while True:
            tok = self._current()
            if tok.type != JSTokenType.PUNCTUATOR:
                break
            op = tok.value
            prec = PRECEDENCE.get(op, 0)
            if prec < min_prec:
                break
            self._advance()
            right = self._parse_binary_expression(min_prec=prec + 1)
            left = JSBinaryExpression(operator=op, left=left, right=right, location=left.location)

        return left

    def _parse_unary_expression(self) -> JSExpression:
        tok = self._current()
        if (tok.type == JSTokenType.PUNCTUATOR and tok.value in ("!", "-", "+", "~")) or (
            tok.type == JSTokenType.KEYWORD and tok.value in ("typeof", "void")
        ):
            self._advance()
            arg = self._parse_unary_expression()
            return JSUnaryExpression(operator=tok.value, argument=arg, prefix=True, location=tok.location)
        return self._parse_call_and_member_expression()

    def _parse_call_and_member_expression(self) -> JSExpression:
        expr = self._parse_primary()

        while True:
            # Function Call: expr(...)
            if self._match("("):
                args: List[JSExpression] = []
                while not self._is_at_end() and self._current().value != ")":
                    args.append(self._parse_assignment_expression())
                    if not self._match(","):
                        break
                self._expect(")")
                expr = JSCallExpression(callee=expr, arguments=args, location=expr.location)
            # Dot Member Access: expr.property
            elif self._match("."):
                prop_tok = self._current()
                self._advance()
                prop = JSIdentifier(name=prop_tok.value, location=prop_tok.location)
                expr = JSMemberExpression(object=expr, property=prop, computed=False, location=expr.location)
            # Computed Bracket Member Access: expr[property]
            elif self._match("["):
                prop_expr = self._parse_expression()
                self._expect("]")
                expr = JSMemberExpression(object=expr, property=prop_expr, computed=True, location=expr.location)
            else:
                break

        return expr

    def _parse_primary(self) -> JSExpression:
        tok = self._current()

        # String literal
        if tok.type == JSTokenType.STRING:
            self._advance()
            return JSLiteral(value=tok.value, raw=repr(tok.value), location=tok.location)

        # Number literal
        if tok.type == JSTokenType.NUMBER:
            self._advance()
            val: Any = None
            try:
                if tok.value.startswith(("0x", "0X")):
                    val = int(tok.value, 16)
                elif tok.value.startswith(("0b", "0B")):
                    val = int(tok.value, 2)
                elif tok.value.startswith(("0o", "0O")):
                    val = int(tok.value, 8)
                elif "." in tok.value or "e" in tok.value.lower():
                    val = float(tok.value)
                else:
                    val = int(tok.value)
            except ValueError:
                val = tok.value
            return JSLiteral(value=val, raw=tok.value, location=tok.location)

        # Boolean and null
        if tok.value == "true":
            self._advance()
            return JSLiteral(value=True, raw="true", location=tok.location)
        if tok.value == "false":
            self._advance()
            return JSLiteral(value=False, raw="false", location=tok.location)
        if tok.value == "null":
            self._advance()
            return JSLiteral(value=None, raw="null", location=tok.location)
        if tok.value == "undefined":
            self._advance()
            return JSIdentifier(name="undefined", location=tok.location)

        # Parenthesized expression or function
        if tok.value == "(":
            self._advance()
            expr = self._parse_expression()
            self._expect(")")
            return expr

        # Array literal [1, 2, 3]
        if tok.value == "[":
            self._advance()
            elements: List[JSExpression] = []
            while not self._is_at_end() and self._current().value != "]":
                elements.append(self._parse_assignment_expression())
                if not self._match(","):
                    break
            self._expect("]")
            return JSArrayExpression(elements=elements, location=tok.location)

        # Object literal { a: 1, 'b': 2 }
        if tok.value == "{":
            self._advance()
            props: List[JSProperty] = []
            while not self._is_at_end() and self._current().value != "}":
                key_tok = self._current()
                self._advance()
                if key_tok.type == JSTokenType.STRING:
                    key_expr: JSExpression = JSLiteral(value=key_tok.value, raw=repr(key_tok.value), location=key_tok.location)
                else:
                    key_expr = JSIdentifier(name=key_tok.value, location=key_tok.location)
                self._expect(":")
                val_expr = self._parse_assignment_expression()
                props.append(JSProperty(key=key_expr, value=val_expr, location=key_tok.location))
                if not self._match(","):
                    break
            self._expect("}")
            return JSObjectExpression(properties=props, location=tok.location)

        # Anonymous Function expression
        if tok.value == "function":
            fn_tok = self._advance()
            fn_id = None
            if self._current().type == JSTokenType.IDENTIFIER:
                id_tok = self._advance()
                fn_id = JSIdentifier(name=id_tok.value, location=id_tok.location)
            self._expect("(")
            params: List[JSIdentifier] = []
            while not self._is_at_end() and self._current().value != ")":
                p_tok = self._advance()
                params.append(JSIdentifier(name=p_tok.value, location=p_tok.location))
                if not self._match(","):
                    break
            self._expect(")")
            body = self._parse_block()
            return JSFunctionExpression(id=fn_id, params=params, body=body, location=fn_tok.location)

        # Identifier
        if tok.type in (JSTokenType.IDENTIFIER, JSTokenType.KEYWORD):
            self._advance()
            return JSIdentifier(name=tok.value, location=tok.location)

        raise ParseError(
            message=f"Unexpected token in expression: '{tok.value}'",
            filename=self.filename,
            lineno=tok.location.start_line,
            col_offset=tok.location.start_col,
        )
