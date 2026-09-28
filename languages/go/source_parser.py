"""Go source code recursive-descent Pratt parser.

Per Section 15 of the Master Specification (Phase 9: Go):
Parses Go source tokens (.go) into a structured GoFile AST:
packages, imports, declarations (func, var, const, type), statements, and expressions.
Maintains exact line and column provenance.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from core.exceptions import ParseError
from languages.go.ast_nodes import (
    GoAssignmentStatement,
    GoBinaryExpression,
    GoBlock,
    GoBranchStatement,
    GoCallExpression,
    GoCaseClause,
    GoCompositeLiteral,
    GoConstSpec,
    GoDecl,
    GoDeferStatement,
    GoExpression,
    GoExpressionStatement,
    GoField,
    GoFile,
    GoForStatement,
    GoFunctionDecl,
    GoGoStatement,
    GoIdentifier,
    GoIfStatement,
    GoImportSpec,
    GoIndexExpression,
    GoKeyValueExpression,
    GoLiteral,
    GoRangeStatement,
    GoReturnStatement,
    GoSelectorExpression,
    GoSliceExpression,
    GoStatement,
    GoSwitchStatement,
    GoTypeAssertExpression,
    GoTypeDecl,
    GoUnaryExpression,
    GoVarSpec,
)
from languages.go.lexer import GoLexer, GoToken, GoTokenType

# Binary operator precedence (lowest to highest)
PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
    "+": 4, "-": 4, "|": 4, "^": 4,
    "*": 5, "/": 5, "%": 5, "<<": 5, ">>": 5, "&": 5, "&^": 5,
}


class GoParser:
    """Parses Go source tokens into Go AST nodes."""

    def __init__(self, source: str, filename: Optional[str] = None) -> None:
        self.filename = filename or "<go>"
        self.source = source
        self.tokens: List[GoToken] = GoLexer(source, filename).tokenize()
        self.pos = 0
        self._in_control_header = False

    def parse(self) -> GoFile:
        """Parses the token stream into a GoFile root AST."""
        # 1. Package declaration
        pkg_name = "main"
        pkg_loc = self._current().location
        if self._match("package"):
            pkg_tok = self._expect_type(GoTokenType.IDENTIFIER)
            pkg_name = pkg_tok.value
            self._consume_semicolons()

        # 2. Imports
        imports: List[GoImportSpec] = []
        while self._match("import"):
            if self._match("("):
                self._consume_semicolons()
                while not self._is_at_end() and self._current().value != ")":
                    imports.append(self._parse_import_spec())
                    self._consume_semicolons()
                self._expect(")")
            else:
                imports.append(self._parse_import_spec())
            self._consume_semicolons()

        # 3. Top-level declarations
        decls: List[GoDecl] = []
        while not self._is_at_end():
            self._consume_semicolons()
            if self._is_at_end():
                break

            decl = self._parse_top_decl()
            if decl:
                decls.append(decl)
            self._consume_semicolons()

        return GoFile(package=pkg_name, imports=imports, decls=decls, location=pkg_loc)

    def _current(self) -> GoToken:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def _peek(self, offset: int = 1) -> GoToken:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def _is_at_end(self) -> bool:
        return self._current().type == GoTokenType.EOF

    def _advance(self) -> GoToken:
        tok = self._current()
        if not self._is_at_end():
            self.pos += 1
        return tok

    def _match(self, value: str) -> Optional[GoToken]:
        if not self._is_at_end() and self._current().value == value:
            return self._advance()
        return None

    def _expect(self, value: str) -> GoToken:
        if self._current().value == value:
            return self._advance()
        tok = self._current()
        raise ParseError(
            f"Expected {value!r}, found {tok.value!r}",
            filename=self.filename,
            lineno=tok.location.start_line,
            col_offset=tok.location.start_col,
        )

    def _expect_type(self, token_type: GoTokenType) -> GoToken:
        if self._current().type == token_type:
            return self._advance()
        tok = self._current()
        raise ParseError(
            f"Expected token of type {token_type.name}, found {tok.type.name} ({tok.value!r})",
            filename=self.filename,
            lineno=tok.location.start_line,
            col_offset=tok.location.start_col,
        )

    def _consume_semicolons(self) -> None:
        while not self._is_at_end() and self._current().value == ";":
            self._advance()

    def _parse_import_spec(self) -> GoImportSpec:
        loc = self._current().location
        alias = None
        if self._current().type == GoTokenType.IDENTIFIER or self._current().value in (".", "_"):
            alias = self._advance().value

        path_tok = self._expect_type(GoTokenType.STRING)
        return GoImportSpec(path=path_tok.value, name=alias, location=loc)

    def _parse_top_decl(self) -> Optional[GoDecl]:
        tok = self._current()
        if tok.value == "func":
            return self._parse_func_decl()
        if tok.value == "const":
            return self._parse_const_decl()
        if tok.value == "var":
            return self._parse_var_decl()
        if tok.value == "type":
            return self._parse_type_decl()

        # Step over unexpected token to recover gracefully
        self._advance()
        return None

    def _parse_func_decl(self) -> GoFunctionDecl:
        func_tok = self._expect("func")
        recv = None
        # Method receiver: func (recv Type) Name(...)
        if self._match("("):
            recv = self._parse_field()
            self._expect(")")

        name_tok = self._expect_type(GoTokenType.IDENTIFIER)
        params, results = self._parse_signature()

        body = None
        if self._current().value == "{":
            body = self._parse_block()

        return GoFunctionDecl(
            name=name_tok.value,
            receiver=recv,
            params=params,
            results=results,
            body=body,
            location=func_tok.location,
        )

    def _parse_signature(self) -> Tuple[List[GoField], List[GoField]]:
        self._expect("(")
        params: List[GoField] = []
        while not self._is_at_end() and self._current().value != ")":
            params.append(self._parse_field())
            if not self._match(","):
                break
        self._expect(")")

        results: List[GoField] = []
        if self._match("("):
            while not self._is_at_end() and self._current().value != ")":
                results.append(self._parse_field())
                if not self._match(","):
                    break
            self._expect(")")
        elif self._current().value not in ("{", ";"):
            # Single return type e.g. func foo() string
            ret_type = self._parse_type_name()
            results.append(GoField(name="", type_name=ret_type))

        return params, results

    def _parse_field(self) -> GoField:
        loc = self._current().location
        name = ""
        # Could be "name type" or just "type"
        first = self._parse_type_name()
        if not self._is_at_end() and self._current().value not in (",", ")", ";", "{", "="):
            second = self._parse_type_name()
            name = first
            type_name = second
        else:
            type_name = first
        return GoField(name=name, type_name=type_name, location=loc)

    def _parse_type_name(self) -> str:
        parts: List[str] = []
        while self._current().value in ("*", "[]", "..."):
            parts.append(self._advance().value)
        if self._match("["):
            size = ""
            if self._current().value != "]":
                size = self._advance().value
            self._expect("]")
            parts.append(f"[{size}]")

        if self._current().type == GoTokenType.IDENTIFIER:
            parts.append(self._advance().value)
            while self._match("."):
                parts.append(".")
                parts.append(self._expect_type(GoTokenType.IDENTIFIER).value)

        return "".join(parts) or "any"

    def _parse_const_decl(self) -> GoConstSpec:
        const_tok = self._expect("const")
        names: List[str] = []
        vals: List[GoExpression] = []
        type_name = None

        if self._match("("):
            self._consume_semicolons()
            while not self._is_at_end() and self._current().value != ")":
                sub_spec = self._parse_single_const()
                names.extend(sub_spec.names)
                vals.extend(sub_spec.values)
                type_name = sub_spec.type_name or type_name
                self._consume_semicolons()
            self._expect(")")
        else:
            sub_spec = self._parse_single_const()
            names = sub_spec.names
            vals = sub_spec.values
            type_name = sub_spec.type_name

        return GoConstSpec(names=names, type_name=type_name, values=vals, location=const_tok.location)

    def _parse_single_const(self) -> GoConstSpec:
        loc = self._current().location
        name_tok = self._expect_type(GoTokenType.IDENTIFIER)
        names = [name_tok.value]
        while self._match(","):
            names.append(self._expect_type(GoTokenType.IDENTIFIER).value)

        type_name = None
        if self._current().value != "=":
            type_name = self._parse_type_name()

        vals: List[GoExpression] = []
        if self._match("="):
            vals.append(self._parse_expression())
            while self._match(","):
                vals.append(self._parse_expression())

        return GoConstSpec(names=names, type_name=type_name, values=vals, location=loc)

    def _parse_var_decl(self) -> GoVarSpec:
        var_tok = self._expect("var")
        names: List[str] = []
        vals: List[GoExpression] = []
        type_name = None

        if self._match("("):
            self._consume_semicolons()
            while not self._is_at_end() and self._current().value != ")":
                sub_spec = self._parse_single_var()
                names.extend(sub_spec.names)
                vals.extend(sub_spec.values)
                type_name = sub_spec.type_name or type_name
                self._consume_semicolons()
            self._expect(")")
        else:
            sub_spec = self._parse_single_var()
            names = sub_spec.names
            vals = sub_spec.values
            type_name = sub_spec.type_name

        return GoVarSpec(names=names, type_name=type_name, values=vals, location=var_tok.location)

    def _parse_single_var(self) -> GoVarSpec:
        loc = self._current().location
        name_tok = self._expect_type(GoTokenType.IDENTIFIER)
        names = [name_tok.value]
        while self._match(","):
            names.append(self._expect_type(GoTokenType.IDENTIFIER).value)

        type_name = None
        if self._current().value != "=":
            type_name = self._parse_type_name()

        vals: List[GoExpression] = []
        if self._match("="):
            vals.append(self._parse_expression())
            while self._match(","):
                vals.append(self._parse_expression())

        return GoVarSpec(names=names, type_name=type_name, values=vals, location=loc)

    def _parse_type_decl(self) -> GoTypeDecl:
        tok = self._expect("type")
        name = self._expect_type(GoTokenType.IDENTIFIER).value
        is_alias = bool(self._match("="))
        type_def = self._parse_type_name()
        return GoTypeDecl(name=name, is_alias=is_alias, type_def=type_def, location=tok.location)

    def _parse_block(self) -> GoBlock:
        start_tok = self._expect("{")
        stmts: List[GoStatement] = []
        self._consume_semicolons()
        while not self._is_at_end() and self._current().value != "}":
            stmt = self._parse_statement()
            if stmt:
                stmts.append(stmt)
            self._consume_semicolons()
        self._expect("}")
        return GoBlock(statements=stmts, location=start_tok.location)

    def _parse_statement(self) -> Optional[GoStatement]:
        tok = self._current()

        if tok.value == ";":
            self._advance()
            return None
        if tok.value == "{":
            return self._parse_block()
        if tok.value == "var":
            var_spec = self._parse_var_decl()
            left = [GoIdentifier(name=n, location=var_spec.location) for n in var_spec.names]
            return GoAssignmentStatement(left=left, operator="=", right=var_spec.values, location=var_spec.location)
        if tok.value == "const":
            const_spec = self._parse_const_decl()
            left = [GoIdentifier(name=n, location=const_spec.location) for n in const_spec.names]
            return GoAssignmentStatement(left=left, operator="=", right=const_spec.values, location=const_spec.location)
        if tok.value == "if":
            return self._parse_if_statement()
        if tok.value == "for":
            return self._parse_for_or_range_statement()
        if tok.value == "return":
            return self._parse_return_statement()
        if tok.value in ("break", "continue", "goto", "fallthrough"):
            op = self._advance().value
            label = None
            if self._current().type == GoTokenType.IDENTIFIER:
                label = self._advance().value
            return GoBranchStatement(token=op, label=label, location=tok.location)
        if tok.value == "defer":
            self._advance()
            call_expr = self._parse_expression()
            if not isinstance(call_expr, GoCallExpression):
                call_expr = GoCallExpression(callee=call_expr, location=tok.location)
            return GoDeferStatement(call=call_expr, location=tok.location)
        if tok.value == "go":
            self._advance()
            call_expr = self._parse_expression()
            if not isinstance(call_expr, GoCallExpression):
                call_expr = GoCallExpression(callee=call_expr, location=tok.location)
            return GoGoStatement(call=call_expr, location=tok.location)
        if tok.value == "switch":
            return self._parse_switch_statement()

        # Expression or assignment statement
        expr = self._parse_expression()
        left_exprs = [expr]
        while self._match(","):
            left_exprs.append(self._parse_expression())

        if self._current().value in (":=", "=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="):
            op = self._advance().value
            right_exprs = [self._parse_expression()]
            while self._match(","):
                right_exprs.append(self._parse_expression())
            return GoAssignmentStatement(left=left_exprs, operator=op, right=right_exprs, location=expr.location)

        if len(left_exprs) == 1:
            return GoExpressionStatement(expression=left_exprs[0], location=left_exprs[0].location)
        return GoExpressionStatement(expression=expr, location=expr.location)

    def _parse_if_statement(self) -> GoIfStatement:
        if_tok = self._expect("if")
        init_stmt = None
        self._in_control_header = True
        cond = self._parse_expression()

        # If followed by semicolon: if init; cond { ... }
        if self._match(";"):
            init_stmt = GoExpressionStatement(expression=cond, location=cond.location)
            cond = self._parse_expression()
        self._in_control_header = False

        body = self._parse_block()
        else_branch = None
        if self._match("else"):
            if self._current().value == "if":
                else_branch = self._parse_if_statement()
            else:
                else_branch = self._parse_block()

        return GoIfStatement(init=init_stmt, condition=cond, body=body, else_branch=else_branch, location=if_tok.location)

    def _parse_for_or_range_statement(self) -> GoStatement:
        for_tok = self._expect("for")
        loc = for_tok.location

        # Infinite loop: for { ... }
        if self._current().value == "{":
            body = self._parse_block()
            return GoForStatement(init=None, condition=None, post=None, body=body, location=loc)

        self._in_control_header = True
        # Look ahead for "range"
        # Cases: for range expr { }, for k := range expr { }, for k, v := range expr { }
        if self._match("range"):
            expr = self._parse_expression()
            self._in_control_header = False
            body = self._parse_block()
            return GoRangeStatement(expression=expr, body=body, location=loc)

        first_expr = self._parse_expression()

        # Check if first is key, val := range ...
        if self._current().value in (",", ":=", "="):
            key = first_expr
            val = None
            if self._match(","):
                val = self._parse_expression()
            op = self._expect_assignment_op()
            if self._match("range"):
                range_expr = self._parse_expression()
                self._in_control_header = False
                body = self._parse_block()
                return GoRangeStatement(key=key, value=val, operator=op, expression=range_expr, body=body, location=loc)
            else:
                # Regular for with init assignment: for i := 0; i < n; i++ { }
                init_stmt = GoAssignmentStatement(left=[key], operator=op, right=[self._parse_expression()], location=loc)
                self._expect(";")
                cond = self._parse_expression() if self._current().value != ";" else None
                self._expect(";")
                post = self._parse_statement() if self._current().value != "{" else None
                self._in_control_header = False
                body = self._parse_block()
                return GoForStatement(init=init_stmt, condition=cond, post=post, body=body, location=loc)

        # While-style for loop: for cond { ... }
        if self._current().value == "{":
            self._in_control_header = False
            body = self._parse_block()
            return GoForStatement(condition=first_expr, body=body, location=loc)

        # 3-part for loop without := init: for i = 0; i < n; i++ { }
        self._expect(";")
        cond = self._parse_expression() if self._current().value != ";" else None
        self._expect(";")
        post = self._parse_statement() if self._current().value != "{" else None
        self._in_control_header = False
        body = self._parse_block()
        init_stmt = GoExpressionStatement(expression=first_expr, location=loc)
        return GoForStatement(init=init_stmt, condition=cond, post=post, body=body, location=loc)

    def _expect_assignment_op(self) -> str:
        if self._current().value in (":=", "="):
            return self._advance().value
        return ":="

    def _parse_return_statement(self) -> GoReturnStatement:
        ret_tok = self._expect("return")
        results: List[GoExpression] = []
        if self._current().value not in (";", "}", ""):
            results.append(self._parse_expression())
            while self._match(","):
                results.append(self._parse_expression())
        return GoReturnStatement(results=results, location=ret_tok.location)

    def _parse_switch_statement(self) -> GoSwitchStatement:
        sw_tok = self._expect("switch")
        tag = None
        if self._current().value != "{":
            tag = self._parse_expression()
        self._expect("{")
        cases: List[GoCaseClause] = []
        self._consume_semicolons()
        while not self._is_at_end() and self._current().value != "}":
            clause_loc = self._current().location
            if self._match("case"):
                case_exprs = [self._parse_expression()]
                while self._match(","):
                    case_exprs.append(self._parse_expression())
                self._expect(":")
                case_stmts: List[GoStatement] = []
                self._consume_semicolons()
                while not self._is_at_end() and self._current().value not in ("case", "default", "}"):
                    s = self._parse_statement()
                    if s:
                        case_stmts.append(s)
                    self._consume_semicolons()
                cases.append(GoCaseClause(cases=case_exprs, body=case_stmts, location=clause_loc))
            elif self._match("default"):
                self._expect(":")
                def_stmts: List[GoStatement] = []
                self._consume_semicolons()
                while not self._is_at_end() and self._current().value not in ("case", "default", "}"):
                    s = self._parse_statement()
                    if s:
                        def_stmts.append(s)
                    self._consume_semicolons()
                cases.append(GoCaseClause(cases=[], body=def_stmts, location=clause_loc))
            else:
                break
        self._expect("}")
        return GoSwitchStatement(tag=tag, cases=cases, location=sw_tok.location)

    # Expression parsing (Pratt precedence)

    def _parse_expression(self) -> GoExpression:
        return self._parse_binary_expression(min_prec=1)

    def _parse_binary_expression(self, min_prec: int) -> GoExpression:
        left = self._parse_unary_expression()

        while True:
            tok = self._current()
            if tok.type != GoTokenType.PUNCTUATOR or tok.value not in PRECEDENCE:
                break

            prec = PRECEDENCE[tok.value]
            if prec < min_prec:
                break

            op = self._advance().value
            right = self._parse_binary_expression(min_prec=prec + 1)
            left = GoBinaryExpression(operator=op, left=left, right=right, location=left.location)

        return left

    def _parse_unary_expression(self) -> GoExpression:
        tok = self._current()
        if tok.type == GoTokenType.PUNCTUATOR and tok.value in ("+", "-", "!", "^", "*", "&", "<-"):
            op = self._advance().value
            operand = self._parse_unary_expression()
            return GoUnaryExpression(operator=op, operand=operand, location=tok.location)
        return self._parse_postfix_expression()

    def _parse_postfix_expression(self) -> GoExpression:
        expr = self._parse_primary()

        while True:
            # Selector: expr.ident
            if self._match("."):
                name = self._expect_type(GoTokenType.IDENTIFIER).value
                expr = GoSelectorExpression(expression=expr, name=name, location=expr.location)
            # Call: expr(args)
            elif self._match("("):
                args: List[GoExpression] = []
                has_ellipsis = False
                while not self._is_at_end() and self._current().value != ")":
                    args.append(self._parse_expression())
                    if self._match("..."):
                        has_ellipsis = True
                        break
                    if not self._match(","):
                        break
                self._expect(")")
                expr = GoCallExpression(callee=expr, args=args, has_ellipsis=has_ellipsis, location=expr.location)
            # Index or Slice: expr[i] or expr[low:high:max]
            elif self._match("["):
                if self._match(":"):
                    # Slice starting with :
                    high = self._parse_expression() if self._current().value not in (":", "]") else None
                    max_idx = None
                    if self._match(":"):
                        max_idx = self._parse_expression()
                    self._expect("]")
                    expr = GoSliceExpression(expression=expr, low=None, high=high, max=max_idx, location=expr.location)
                else:
                    first = self._parse_expression()
                    if self._match(":"):
                        high = self._parse_expression() if self._current().value not in (":", "]") else None
                        max_idx = None
                        if self._match(":"):
                            max_idx = self._parse_expression()
                        self._expect("]")
                        expr = GoSliceExpression(expression=expr, low=first, high=high, max=max_idx, location=expr.location)
                    else:
                        self._expect("]")
                        expr = GoIndexExpression(expression=expr, index=first, location=expr.location)
            # Postfix ++ or --
            elif self._current().value in ("++", "--"):
                op = self._advance().value
                expr = GoUnaryExpression(operator=op, operand=expr, location=expr.location)
            else:
                break

        return expr

    def _parse_primary(self) -> GoExpression:
        tok = self._current()

        # Grouped expression: (expr)
        if self._match("("):
            expr = self._parse_expression()
            self._expect(")")
            return expr

        # Composite literal or Slice type creation: []byte{ ... } or Type{ ... }
        if tok.value == "[]" or (tok.type == GoTokenType.PUNCTUATOR and tok.value == "["):
            type_name = self._parse_type_name()
            if self._current().value == "{":
                return self._parse_composite_literal(type_name, tok.location)

        # String literal
        if tok.type == GoTokenType.STRING:
            self._advance()
            return GoLiteral(value=tok.value, raw=repr(tok.value), type_name="string", location=tok.location)

        # Rune literal
        if tok.type == GoTokenType.RUNE:
            self._advance()
            return GoLiteral(value=tok.value, raw=f"'{tok.value}'", type_name="rune", location=tok.location)

        # Number literal
        if tok.type == GoTokenType.NUMBER:
            self._advance()
            val = self._evaluate_number(tok.value)
            tname = "float64" if isinstance(val, float) else "int"
            return GoLiteral(value=val, raw=tok.value, type_name=tname, location=tok.location)

        # Boolean and nil
        if tok.value == "true":
            self._advance()
            return GoLiteral(value=True, raw="true", type_name="bool", location=tok.location)
        if tok.value == "false":
            self._advance()
            return GoLiteral(value=False, raw="false", type_name="bool", location=tok.location)
        if tok.value == "nil":
            self._advance()
            return GoLiteral(value=None, raw="nil", type_name="nil", location=tok.location)

        # Identifier (or potential composite literal Type{ ... })
        if tok.type == GoTokenType.IDENTIFIER:
            ident = self._advance()
            if not self._in_control_header and ident.value and ident.value[0].isupper() and self._current().value == "{":
                return self._parse_composite_literal(ident.value, ident.location)
            return GoIdentifier(name=ident.value, location=ident.location)

        raise ParseError(
            f"Unexpected token in Go expression: {tok.value!r}",
            filename=self.filename,
            lineno=tok.location.start_line,
            col_offset=tok.location.start_col,
        )

    def _parse_composite_literal(self, type_name: str, loc: Any) -> GoCompositeLiteral:
        self._expect("{")
        elements: List[GoExpression] = []
        self._consume_semicolons()
        while not self._is_at_end() and self._current().value != "}":
            elem = self._parse_expression()
            if self._match(":"):
                val = self._parse_expression()
                elem = GoKeyValueExpression(key=elem, value=val, location=elem.location)
            elements.append(elem)
            self._match(",")
            self._consume_semicolons()
        self._expect("}")
        return GoCompositeLiteral(type_name=type_name, elements=elements, location=loc)

    def _evaluate_number(self, raw: str) -> Any:
        clean = raw.replace("_", "")
        try:
            if clean.startswith(("0x", "0X")):
                return int(clean, 16)
            if clean.startswith(("0b", "0B")):
                return int(clean, 2)
            if clean.startswith(("0o", "0O")):
                return int(clean, 8)
            if "." in clean or "e" in clean.lower():
                return float(clean)
            return int(clean, 0)
        except ValueError:
            return raw
