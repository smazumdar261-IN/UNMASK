"""Java AST to Common IR bidirectional converter.

Per Section 14 and Section 16 of the Master Specification (Phase 8: Java):
Bridges Java AST and the Common Intermediate Representation (IR),
allowing analysis passes to operate on Java constructs independently of syntax.
"""

from __future__ import annotations

from typing import Any, List, Optional

from core.ir import (
    IRAssignment,
    IRBinaryOperation,
    IRBranch,
    IRCall,
    IRConstant,
    IRExpression,
    IRFunction,
    IRLoop,
    IRModule,
    IRNode,
    IRReturn,
    IRStatement,
    IRUnaryOperation,
    IRVariable,
)
from languages.java.ast_nodes import (
    JavaAssignmentExpression,
    JavaBinaryExpression,
    JavaBlock,
    JavaClassDeclaration,
    JavaCompilationUnit,
    JavaExpression,
    JavaExpressionStatement,
    JavaFieldAccess,
    JavaIdentifier,
    JavaIfStatement,
    JavaLiteral,
    JavaMethodCall,
    JavaMethodDeclaration,
    JavaParameter,
    JavaReturnStatement,
    JavaStatement,
    JavaUnaryExpression,
    JavaVariableDeclarationStatement,
    JavaWhileStatement,
)


class JavaIRConverter:
    """Converts between Java AST and Common IR."""

    @classmethod
    def to_ir(cls, unit: JavaCompilationUnit) -> IRModule:
        """Converts a JavaCompilationUnit into a Common IRModule."""
        ir_stmts: List[IRStatement] = []

        for type_decl in unit.types:
            if isinstance(type_decl, JavaClassDeclaration):
                for member in type_decl.members:
                    if isinstance(member, JavaMethodDeclaration):
                        ir_fn = cls._convert_method_to_ir(member, class_name=type_decl.name)
                        ir_stmts.append(ir_fn)

        return IRModule(name=unit.package.name if unit.package else "<java>", language="java", body=ir_stmts)

    @classmethod
    def _convert_method_to_ir(cls, method: JavaMethodDeclaration, class_name: str) -> IRFunction:
        params = [p.name for p in method.parameters]
        body_stmts: List[IRStatement] = []
        if method.body:
            for s in method.body.statements:
                converted = cls._convert_statement_to_ir(s)
                if converted:
                    body_stmts.append(converted)

        full_name = f"{class_name}.{method.name}" if class_name else method.name
        return IRFunction(
            name=full_name,
            parameters=params,
            body=body_stmts,
            return_type=method.return_type,
        )

    @classmethod
    def _convert_statement_to_ir(cls, stmt: JavaStatement) -> Optional[IRStatement]:
        if isinstance(stmt, JavaVariableDeclarationStatement):
            val = cls._convert_expression_to_ir(stmt.initializer) if stmt.initializer else IRConstant(value=None)
            return IRAssignment(target=IRVariable(name=stmt.name), value=val, location=stmt.location)

        if isinstance(stmt, JavaExpressionStatement):
            expr = stmt.expression
            if isinstance(expr, JavaAssignmentExpression) and isinstance(expr.target, JavaIdentifier):
                val = cls._convert_expression_to_ir(expr.value)
                return IRAssignment(target=IRVariable(name=expr.target.name), value=val, location=stmt.location)
            # Other expression statements represented as IRCall or IRAssignment
            converted_expr = cls._convert_expression_to_ir(expr)
            if isinstance(converted_expr, IRCall):
                return IRAssignment(target=IRVariable(name="_"), value=converted_expr, location=stmt.location)
            return None

        if isinstance(stmt, JavaIfStatement):
            cond = cls._convert_expression_to_ir(stmt.condition)
            body: List[IRStatement] = []
            if isinstance(stmt.then_branch, JavaBlock):
                for s in stmt.then_branch.statements:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        body.append(cs)
            else:
                cs = cls._convert_statement_to_ir(stmt.then_branch)
                if cs:
                    body.append(cs)

            orelse: List[IRStatement] = []
            if stmt.else_branch:
                if isinstance(stmt.else_branch, JavaBlock):
                    for s in stmt.else_branch.statements:
                        cs = cls._convert_statement_to_ir(s)
                        if cs:
                            orelse.append(cs)
                else:
                    cs = cls._convert_statement_to_ir(stmt.else_branch)
                    if cs:
                        orelse.append(cs)

            return IRBranch(condition=cond, body=body, orelse=orelse, location=stmt.location)

        if isinstance(stmt, JavaWhileStatement):
            cond = cls._convert_expression_to_ir(stmt.condition)
            body = []
            if isinstance(stmt.body, JavaBlock):
                for s in stmt.body.statements:
                    cs = cls._convert_statement_to_ir(s)
                    if cs:
                        body.append(cs)
            return IRLoop(condition=cond, body=body, location=stmt.location)

        if isinstance(stmt, JavaReturnStatement):
            val = cls._convert_expression_to_ir(stmt.expression) if stmt.expression else None
            return IRReturn(value=val, location=stmt.location)

        return None

    @classmethod
    def _convert_expression_to_ir(cls, expr: Optional[JavaExpression]) -> IRExpression:
        if expr is None:
            return IRConstant(value=None)

        if isinstance(expr, JavaLiteral):
            return IRConstant(value=expr.value, type_name=expr.type_name, location=expr.location)

        if isinstance(expr, JavaIdentifier):
            return IRVariable(name=expr.name, location=expr.location)

        if isinstance(expr, JavaBinaryExpression):
            return IRBinaryOperation(
                op=expr.operator,
                left=cls._convert_expression_to_ir(expr.left),
                right=cls._convert_expression_to_ir(expr.right),
                location=expr.location,
            )

        if isinstance(expr, JavaUnaryExpression):
            return IRUnaryOperation(
                op=expr.operator,
                operand=cls._convert_expression_to_ir(expr.operand),
                location=expr.location,
            )

        if isinstance(expr, JavaMethodCall):
            callee_name = expr.name
            if expr.target:
                callee_name = f"{cls._format_target(expr.target)}.{expr.name}"
            args = [cls._convert_expression_to_ir(a) for a in expr.arguments]
            return IRCall(callee=IRVariable(name=callee_name), args=args, location=expr.location)

        if isinstance(expr, JavaFieldAccess):
            full_name = f"{cls._format_target(expr.target)}.{expr.name}"
            return IRVariable(name=full_name, location=expr.location)

        return IRConstant(value=None, location=expr.location)

    @classmethod
    def _format_target(cls, target: JavaExpression) -> str:
        if isinstance(target, JavaIdentifier):
            return target.name
        if isinstance(target, JavaFieldAccess):
            return f"{cls._format_target(target.target)}.{target.name}"
        return "target"

    @classmethod
    def from_ir(cls, ir_module: IRModule) -> JavaCompilationUnit:
        """Converts a Common IRModule back into a JavaCompilationUnit AST."""
        classes_map: dict[str, list[JavaMethodDeclaration]] = {}
        for stmt in ir_module.body:
            if isinstance(stmt, IRFunction):
                parts = stmt.name.split(".", 1)
                cls_name = parts[0] if len(parts) > 1 else "Decompiled"
                m_name = parts[1] if len(parts) > 1 else stmt.name

                params = [JavaParameter(type_name="Object", name=p) for p in stmt.parameters]
                body_stmts = [cls._convert_ir_to_statement(s) for s in stmt.body]
                method_decl = JavaMethodDeclaration(
                    modifiers=["public", "static"],
                    return_type=stmt.return_type or "void",
                    name=m_name,
                    parameters=params,
                    body=JavaBlock(statements=body_stmts),
                )
                classes_map.setdefault(cls_name, []).append(method_decl)

        type_decls = []
        for cls_name, methods in classes_map.items():
            type_decls.append(
                JavaClassDeclaration(
                    modifiers=["public"],
                    name=cls_name,
                    members=methods,
                )
            )

        pkg = None
        if ir_module.name and ir_module.name not in ("<java>", "<module>"):
            from languages.java.ast_nodes import JavaPackageDeclaration
            pkg = JavaPackageDeclaration(name=ir_module.name)

        return JavaCompilationUnit(package=pkg, imports=[], types=type_decls)

    @classmethod
    def _convert_ir_to_statement(cls, stmt: IRStatement) -> JavaStatement:
        from core.ir import IRExpressionStatement, IRMemberAccess
        if isinstance(stmt, IRExpressionStatement):
            return JavaExpressionStatement(expression=cls._convert_ir_to_expression(stmt.expression))
        if isinstance(stmt, IRAssignment):
            val_expr = cls._convert_ir_to_expression(stmt.value)
            target_name = stmt.target.name if isinstance(stmt.target, IRVariable) else "_"
            if target_name == "_":
                return JavaExpressionStatement(expression=val_expr)
            return JavaVariableDeclarationStatement(
                type_name="var",
                name=target_name,
                initializer=val_expr,
            )
        if isinstance(stmt, IRReturn):
            val = cls._convert_ir_to_expression(stmt.value) if stmt.value else None
            return JavaReturnStatement(expression=val)
        if isinstance(stmt, IRBranch):
            cond = cls._convert_ir_to_expression(stmt.condition)
            then_body = JavaBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.body])
            else_body = JavaBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.orelse]) if stmt.orelse else None
            return JavaIfStatement(condition=cond, then_branch=then_body, else_branch=else_body)
        if isinstance(stmt, IRLoop):
            cond = cls._convert_ir_to_expression(stmt.condition) if stmt.condition else JavaLiteral(value=True, raw="true")
            loop_body = JavaBlock(statements=[cls._convert_ir_to_statement(s) for s in stmt.body])
            return JavaWhileStatement(condition=cond, body=loop_body)
        return JavaExpressionStatement(expression=JavaLiteral(value=None, raw="null"))

    @classmethod
    def _convert_ir_to_expression(cls, expr: Optional[IRExpression]) -> JavaExpression:
        from core.ir import IRMemberAccess
        if expr is None:
            return JavaLiteral(value=None, raw="null")
        if isinstance(expr, IRMemberAccess):
            target = cls._convert_ir_to_expression(expr.target)
            return JavaFieldAccess(target=target, name=expr.member)
        if isinstance(expr, IRConstant):
            return JavaLiteral(value=expr.value, raw=repr(expr.value) if expr.value is not None else "null", type_name=expr.type_name)
        if isinstance(expr, IRVariable):
            if "." in expr.name:
                parts = expr.name.split(".")
                curr: JavaExpression = JavaIdentifier(name=parts[0])
                for part in parts[1:]:
                    curr = JavaFieldAccess(target=curr, name=part)
                return curr
            return JavaIdentifier(name=expr.name)
        if isinstance(expr, IRBinaryOperation):
            return JavaBinaryExpression(
                operator=expr.op,
                left=cls._convert_ir_to_expression(expr.left),
                right=cls._convert_ir_to_expression(expr.right),
            )
        if isinstance(expr, IRUnaryOperation):
            return JavaUnaryExpression(
                operator=expr.op,
                operand=cls._convert_ir_to_expression(expr.operand),
            )
        if isinstance(expr, IRCall):
            target = None
            method_name = ""
            if isinstance(expr.callee, IRVariable):
                parts = expr.callee.name.split(".")
                if len(parts) > 1:
                    target = JavaIdentifier(name=".".join(parts[:-1]))
                    method_name = parts[-1]
                else:
                    method_name = parts[0]
            args = [cls._convert_ir_to_expression(a) for a in expr.args]
            return JavaMethodCall(target=target, name=method_name, arguments=args)
        return JavaLiteral(value=None, raw="null")

