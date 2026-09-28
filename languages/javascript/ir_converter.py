"""JavaScript AST to Common IR bidirectional converter.

Per Section 12 and Section 16 of the Master Specification:
Bridges JavaScript AST and Common Intermediate Representation (IR),
enabling universal language-neutral deobfuscation passes on JavaScript code.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRBlock,
    IRBranch,
    IRBreak,
    IRCall,
    IRConstant,
    IRContinue,
    IRDictLiteral,
    IRExpression,
    IRExpressionStatement,
    IRFunction,
    IRIndexAccess,
    IRListLiteral,
    IRLoop,
    IRMemberAccess,
    IRModule,
    IRPass,
    IRReturn,
    IRStatement,
    IRString,
    IRUnaryOperation,
    IRVariable,
)
from languages.javascript.ast_nodes import (
    JSArrayExpression,
    JSAssignmentExpression,
    JSBinaryExpression,
    JSBlockStatement,
    JSBreakStatement,
    JSCallExpression,
    JSContinueStatement,
    JSEmptyStatement,
    JSExpression,
    JSExpressionStatement,
    JSForStatement,
    JSFunctionDeclaration,
    JSIdentifier,
    JSIfStatement,
    JSLiteral,
    JSMemberExpression,
    JSNode,
    JSObjectExpression,
    JSProgram,
    JSProperty,
    JSReturnStatement,
    JSStatement,
    JSUnaryExpression,
    JSVariableDeclaration,
    JSVariableDeclarator,
    JSWhileStatement,
)


class JSIRConverter:
    """Converts between JavaScript AST and Common IR."""

    @classmethod
    def to_ir(cls, prog: JSProgram) -> IRModule:
        """Converts a JSProgram AST into a Common IRModule."""
        ir_stmts: List[IRStatement] = []
        for stmt in prog.body:
            converted = cls._convert_statement_to_ir(stmt)
            if converted:
                if isinstance(converted, list):
                    ir_stmts.extend(converted)
                else:
                    ir_stmts.append(converted)

        return IRModule(
            name="<javascript>",
            language="javascript",
            body=ir_stmts,
            location=prog.location,
        )

    @classmethod
    def _convert_statement_to_ir(cls, stmt: JSStatement) -> Optional[Union[IRStatement, List[IRStatement]]]:
        if isinstance(stmt, JSFunctionDeclaration):
            fn_name = stmt.id.name if stmt.id else "anonymous"
            params: List[str] = []
            for p in stmt.params:
                if isinstance(p, JSIdentifier):
                    params.append(p.name)
                elif hasattr(p, "id") and hasattr(p.id, "name"):
                    params.append(p.id.name)
                elif hasattr(p, "name"):
                    params.append(getattr(p, "name"))
                else:
                    params.append(str(p))

            body_stmts: List[IRStatement] = []
            if stmt.body and isinstance(stmt.body, JSBlockStatement):
                for s in stmt.body.body:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        if isinstance(cs, list):
                            body_stmts.extend(cs)
                        else:
                            body_stmts.append(cs)

            ret_type = str(stmt.return_type) if stmt.return_type else None
            return IRFunction(
                name=fn_name,
                parameters=params,
                body=body_stmts,
                return_type=ret_type,
                location=stmt.location,
            )

        if isinstance(stmt, JSVariableDeclaration):
            results: List[IRStatement] = []
            for decl in stmt.declarations:
                val = cls._convert_expression_to_ir(decl.init) if decl.init else IRConstant(value=None)
                target = IRVariable(name=decl.id.name, location=decl.id.location)
                assignment = IRAssignment(target=target, value=val, location=decl.location)
                assignment.metadata["kind"] = stmt.kind
                results.append(assignment)
            return results if len(results) > 1 else results[0] if results else None

        if isinstance(stmt, JSExpressionStatement):
            expr = stmt.expression
            if isinstance(expr, JSAssignmentExpression):
                target = cls._convert_expression_to_ir(expr.left)
                val = cls._convert_expression_to_ir(expr.right)
                return IRAssignment(target=target, value=val, location=stmt.location)
            converted_expr = cls._convert_expression_to_ir(expr)
            return IRExpressionStatement(expression=converted_expr, location=stmt.location)

        if isinstance(stmt, JSIfStatement):
            cond = cls._convert_expression_to_ir(stmt.test)
            body: List[IRStatement] = []
            if isinstance(stmt.consequent, JSBlockStatement):
                for s in stmt.consequent.body:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        if isinstance(cs, list):
                            body.extend(cs)
                        else:
                            body.append(cs)
            else:
                cs = cls._convert_statement_to_ir(stmt.consequent)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)

            orelse: List[IRStatement] = []
            if stmt.alternate:
                if isinstance(stmt.alternate, JSBlockStatement):
                    for s in stmt.alternate.body:
                        cs = cls._convert_statement_to_ir(s)
                        if cs:
                            if isinstance(cs, list):
                                orelse.extend(cs)
                            else:
                                orelse.append(cs)
                else:
                    cs = cls._convert_statement_to_ir(stmt.alternate)
                    if cs:
                        if isinstance(cs, list):
                            orelse.extend(cs)
                        else:
                            orelse.append(cs)

            return IRBranch(condition=cond, body=body, orelse=orelse, location=stmt.location)

        if isinstance(stmt, JSWhileStatement):
            cond = cls._convert_expression_to_ir(stmt.test)
            body = []
            if isinstance(stmt.body, JSBlockStatement):
                for s in stmt.body.body:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        if isinstance(cs, list):
                            body.extend(cs)
                        else:
                            body.append(cs)
            else:
                cs = cls._convert_statement_to_ir(stmt.body)
                if cs:
                    if isinstance(cs, list):
                        body.extend(cs)
                    else:
                        body.append(cs)
            return IRLoop(condition=cond, body=body, is_for=False, location=stmt.location)

        if isinstance(stmt, JSForStatement):
            body = []
            if isinstance(stmt.body, JSBlockStatement):
                for s in stmt.body.body:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        if isinstance(cs, list):
                            body.extend(cs)
                        else:
                            body.append(cs)
            cond = cls._convert_expression_to_ir(stmt.test) if stmt.test else IRConstant(value=True)
            return IRLoop(condition=cond, body=body, is_for=False, location=stmt.location)

        if isinstance(stmt, JSReturnStatement):
            val = cls._convert_expression_to_ir(stmt.argument) if stmt.argument else None
            return IRReturn(value=val, location=stmt.location)

        if isinstance(stmt, JSBreakStatement):
            return IRBreak(label=stmt.label, location=stmt.location)

        if isinstance(stmt, JSContinueStatement):
            return IRContinue(label=stmt.label, location=stmt.location)

        if isinstance(stmt, JSEmptyStatement):
            return IRPass(location=stmt.location)

        if isinstance(stmt, JSBlockStatement):
            block_stmts: List[IRStatement] = []
            for s in stmt.body:
                cs = cls._convert_statement_to_ir(s)
                if cs:
                    if isinstance(cs, list):
                        block_stmts.extend(cs)
                    else:
                        block_stmts.append(cs)
            return IRBlock(statements=block_stmts, location=stmt.location)

        return None

    @classmethod
    def _convert_expression_to_ir(cls, expr: Optional[JSExpression]) -> IRExpression:
        if expr is None:
            return IRConstant(value=None)

        if isinstance(expr, JSLiteral):
            if isinstance(expr.value, str):
                return IRString(value=expr.value, location=expr.location)
            return IRConstant(value=expr.value, location=expr.location)

        if isinstance(expr, JSIdentifier):
            return IRVariable(name=expr.name, location=expr.location)

        if isinstance(expr, JSMemberExpression):
            obj = cls._convert_expression_to_ir(expr.object)
            if not expr.computed and isinstance(expr.property, JSIdentifier):
                return IRMemberAccess(target=obj, member=expr.property.name, location=expr.location)
            else:
                idx = cls._convert_expression_to_ir(expr.property)
                return IRIndexAccess(target=obj, index=idx, location=expr.location)

        if isinstance(expr, JSBinaryExpression):
            return IRBinaryOperation(
                op=expr.operator,
                left=cls._convert_expression_to_ir(expr.left),
                right=cls._convert_expression_to_ir(expr.right),
                location=expr.location,
            )

        if isinstance(expr, JSUnaryExpression):
            return IRUnaryOperation(
                op=expr.operator,
                operand=cls._convert_expression_to_ir(expr.argument),
                location=expr.location,
            )

        if isinstance(expr, JSCallExpression):
            callee = cls._convert_expression_to_ir(expr.callee)
            args = [cls._convert_expression_to_ir(a) for a in expr.arguments]
            return IRCall(callee=callee, args=args, location=expr.location)

        if isinstance(expr, JSArrayExpression):
            elements = [cls._convert_expression_to_ir(e) for e in expr.elements if e is not None]
            return IRListLiteral(elements=elements, location=expr.location)

        if isinstance(expr, JSObjectExpression):
            keys: List[IRExpression] = []
            vals: List[IRExpression] = []
            for prop in expr.properties:
                if isinstance(prop, JSProperty):
                    k_str = prop.key.name if isinstance(prop.key, JSIdentifier) else str(prop.key)
                    keys.append(IRString(value=k_str))
                    vals.append(cls._convert_expression_to_ir(prop.value))
            return IRDictLiteral(keys=keys, values=vals, location=expr.location)

        return IRConstant(value=None, location=expr.location)

    @classmethod
    def from_ir(cls, ir_module: IRModule) -> JSProgram:
        """Converts a Common IRModule back into a JSProgram AST."""
        js_stmts: List[JSStatement] = []
        for s in ir_module.body:
            converted = cls._convert_ir_to_stmt(s)
            if converted:
                js_stmts.append(converted)

        return JSProgram(body=js_stmts, location=ir_module.location)

    @classmethod
    def _convert_ir_to_stmt(cls, stmt: IRStatement) -> Optional[JSStatement]:
        if isinstance(stmt, IRFunction):
            params = [JSIdentifier(name=p) for p in stmt.parameters]
            body_stmts = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body_stmts = [s for s in body_stmts if s is not None]
            return JSFunctionDeclaration(
                id=JSIdentifier(name=stmt.name),
                params=params,
                body=JSBlockStatement(body=body_stmts),
                location=stmt.location,
            )

        if isinstance(stmt, IRAssignment):
            val = cls._convert_ir_to_expr(stmt.value)
            kind = stmt.metadata.get("kind", "var")
            if isinstance(stmt.target, IRVariable):
                target_id = JSIdentifier(name=stmt.target.name)
                declarator = JSVariableDeclarator(id=target_id, init=val)
                return JSVariableDeclaration(kind=kind, declarations=[declarator], location=stmt.location)
            else:
                left = cls._convert_ir_to_expr(stmt.target)
                assign_expr = JSAssignmentExpression(operator="=", left=left, right=val)
                return JSExpressionStatement(expression=assign_expr, location=stmt.location)

        if isinstance(stmt, IRExpressionStatement):
            expr = cls._convert_ir_to_expr(stmt.expression)
            return JSExpressionStatement(expression=expr, location=stmt.location)

        if isinstance(stmt, IRBranch):
            cond = cls._convert_ir_to_expr(stmt.condition)
            body_stmts = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body_stmts = [s for s in body_stmts if s is not None]
            then_block = JSBlockStatement(body=body_stmts)

            else_block = None
            if stmt.orelse:
                else_stmts = [cls._convert_ir_to_stmt(s) for s in stmt.orelse]
                else_stmts = [s for s in else_stmts if s is not None]
                else_block = JSBlockStatement(body=else_stmts)

            return JSIfStatement(
                test=cond,
                consequent=then_block,
                alternate=else_block,
                location=stmt.location,
            )

        if isinstance(stmt, IRLoop):
            cond = cls._convert_ir_to_expr(stmt.condition) if stmt.condition else JSLiteral(value=True, raw="true")
            body_stmts = [cls._convert_ir_to_stmt(s) for s in stmt.body]
            body_stmts = [s for s in body_stmts if s is not None]
            return JSWhileStatement(
                test=cond,
                body=JSBlockStatement(body=body_stmts),
                location=stmt.location,
            )

        if isinstance(stmt, IRReturn):
            val = cls._convert_ir_to_expr(stmt.value) if stmt.value else None
            return JSReturnStatement(argument=val, location=stmt.location)

        if isinstance(stmt, IRBreak):
            return JSBreakStatement(label=stmt.label, location=stmt.location)

        if isinstance(stmt, IRContinue):
            return JSContinueStatement(label=stmt.label, location=stmt.location)

        if isinstance(stmt, IRPass):
            return JSEmptyStatement(location=stmt.location)

        if isinstance(stmt, IRBlock):
            b_stmts = [cls._convert_ir_to_stmt(s) for s in stmt.statements]
            b_stmts = [s for s in b_stmts if s is not None]
            return JSBlockStatement(body=b_stmts, location=stmt.location)

        return None

    @classmethod
    def _convert_ir_to_expr(cls, expr: Optional[IRExpression]) -> JSExpression:
        if expr is None:
            return JSLiteral(value=None, raw="null")

        if isinstance(expr, IRConstant):
            if isinstance(expr.value, str):
                return JSLiteral(value=expr.value, raw=repr(expr.value), location=expr.location)
            if expr.value is None:
                return JSLiteral(value=None, raw="null", location=expr.location)
            if isinstance(expr.value, bool):
                return JSLiteral(value=expr.value, raw="true" if expr.value else "false", location=expr.location)
            return JSLiteral(value=expr.value, raw=str(expr.value), location=expr.location)

        if isinstance(expr, IRVariable):
            return JSIdentifier(name=expr.name, location=expr.location)

        if isinstance(expr, IRMemberAccess):
            target = cls._convert_ir_to_expr(expr.target)
            prop = JSIdentifier(name=expr.member)
            return JSMemberExpression(object=target, property=prop, computed=False, location=expr.location)

        if isinstance(expr, IRIndexAccess):
            target = cls._convert_ir_to_expr(expr.target)
            idx = cls._convert_ir_to_expr(expr.index)
            return JSMemberExpression(object=target, property=idx, computed=True, location=expr.location)

        if isinstance(expr, IRBinaryOperation):
            left = cls._convert_ir_to_expr(expr.left)
            right = cls._convert_ir_to_expr(expr.right)
            return JSBinaryExpression(
                operator=expr.op,
                left=left,
                right=right,
                location=expr.location,
            )

        if isinstance(expr, IRUnaryOperation):
            operand = cls._convert_ir_to_expr(expr.operand)
            return JSUnaryExpression(
                operator=expr.op,
                argument=operand,
                prefix=True,
                location=expr.location,
            )

        if isinstance(expr, IRCall):
            callee = cls._convert_ir_to_expr(expr.callee)
            args = [cls._convert_ir_to_expr(a) for a in expr.args]
            return JSCallExpression(callee=callee, arguments=args, location=expr.location)

        if isinstance(expr, IRListLiteral):
            elements = [cls._convert_ir_to_expr(e) for e in expr.elements]
            return JSArrayExpression(elements=elements, location=expr.location)

        if isinstance(expr, IRDictLiteral):
            props = []
            for k, v in zip(expr.keys, expr.values):
                k_expr = cls._convert_ir_to_expr(k)
                v_expr = cls._convert_ir_to_expr(v)
                props.append(JSProperty(key=k_expr, value=v_expr))
            return JSObjectExpression(properties=props, location=expr.location)

        return JSLiteral(value=None, raw="null")
