"""JVM .class bytecode reader and decompiler.

Per Section 14 of the Master Specification (Phase 8: Java - Bytecode mode):
Reads binary JVM class files and ZIP/JAR archives using Python stdlib (struct, zipfile).
Reconstructs constant pool, class structure, fields, methods, and decompiles
bytecode instructions into Java AST and Common IR.
"""

from __future__ import annotations

import io
import struct
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from core.exceptions import ParseError
from languages.java.ast_nodes import (
    JavaBinaryExpression,
    JavaBlock,
    JavaClassDeclaration,
    JavaCompilationUnit,
    JavaExpression,
    JavaExpressionStatement,
    JavaFieldAccess,
    JavaFieldDeclaration,
    JavaIdentifier,
    JavaLiteral,
    JavaMethodCall,
    JavaMethodDeclaration,
    JavaNewClassExpression,
    JavaParameter,
    JavaReturnStatement,
    JavaStatement,
    JavaVariableDeclarationStatement,
)

# Constant pool tags
CONSTANT_Utf8 = 1
CONSTANT_Integer = 3
CONSTANT_Float = 4
CONSTANT_Long = 5
CONSTANT_Double = 6
CONSTANT_Class = 7
CONSTANT_String = 8
CONSTANT_Fieldref = 9
CONSTANT_Methodref = 10
CONSTANT_InterfaceMethodref = 11
CONSTANT_NameAndType = 12
CONSTANT_MethodHandle = 15
CONSTANT_MethodType = 16
CONSTANT_InvokeDynamic = 18

# Access flags
ACC_PUBLIC = 0x0001
ACC_PRIVATE = 0x0002
ACC_PROTECTED = 0x0004
ACC_STATIC = 0x0008
ACC_FINAL = 0x0010
ACC_INTERFACE = 0x0200
ACC_ABSTRACT = 0x0400


class ClassFileReader:
    """Parses binary Java .class bytecode file."""

    def __init__(self, data: bytes, filename: Optional[str] = None) -> None:
        self.stream = io.BytesIO(data)
        self.filename = filename or "<class>"
        self.constant_pool: Dict[int, Any] = {}
        self.access_flags: int = 0
        self.this_class: str = ""
        self.super_class: str = ""
        self.interfaces: List[str] = []
        self.fields: List[Dict[str, Any]] = []
        self.methods: List[Dict[str, Any]] = []
        self._parse()

    def _read_bytes(self, length: int) -> bytes:
        b = self.stream.read(length)
        if len(b) < length:
            raise ParseError(f"Unexpected EOF reading {length} bytes from class file", filename=self.filename)
        return b

    def _read_u1(self) -> int:
        return self._read_bytes(1)[0]

    def _read_u2(self) -> int:
        return struct.unpack(">H", self._read_bytes(2))[0]

    def _read_u4(self) -> int:
        return struct.unpack(">I", self._read_bytes(4))[0]

    def _parse(self) -> None:
        magic = self._read_u4()
        if magic != 0xCAFEBABE:
            raise ParseError(f"Invalid Java class file magic: 0x{magic:08X}", filename=self.filename)

        self.minor_version = self._read_u2()
        self.major_version = self._read_u2()
        cp_count = self._read_u2()

        # Parse constant pool (1-indexed)
        idx = 1
        while idx < cp_count:
            tag = self._read_u1()
            if tag == CONSTANT_Utf8:
                length = self._read_u2()
                val_bytes = self._read_bytes(length)
                self.constant_pool[idx] = (tag, val_bytes.decode("utf-8", errors="replace"))
            elif tag == CONSTANT_Integer:
                val = struct.unpack(">i", self._read_bytes(4))[0]
                self.constant_pool[idx] = (tag, val)
            elif tag == CONSTANT_Float:
                val = struct.unpack(">f", self._read_bytes(4))[0]
                self.constant_pool[idx] = (tag, val)
            elif tag == CONSTANT_Long:
                val = struct.unpack(">q", self._read_bytes(8))[0]
                self.constant_pool[idx] = (tag, val)
                idx += 1  # 8-byte constants take 2 entries
            elif tag == CONSTANT_Double:
                val = struct.unpack(">d", self._read_bytes(8))[0]
                self.constant_pool[idx] = (tag, val)
                idx += 1
            elif tag == CONSTANT_Class:
                name_idx = self._read_u2()
                self.constant_pool[idx] = (tag, name_idx)
            elif tag == CONSTANT_String:
                string_idx = self._read_u2()
                self.constant_pool[idx] = (tag, string_idx)
            elif tag in (CONSTANT_Fieldref, CONSTANT_Methodref, CONSTANT_InterfaceMethodref):
                cls_idx = self._read_u2()
                nat_idx = self._read_u2()
                self.constant_pool[idx] = (tag, cls_idx, nat_idx)
            elif tag == CONSTANT_NameAndType:
                name_idx = self._read_u2()
                desc_idx = self._read_u2()
                self.constant_pool[idx] = (tag, name_idx, desc_idx)
            elif tag == CONSTANT_MethodHandle:
                kind = self._read_u1()
                ref_idx = self._read_u2()
                self.constant_pool[idx] = (tag, kind, ref_idx)
            elif tag == CONSTANT_MethodType:
                desc_idx = self._read_u2()
                self.constant_pool[idx] = (tag, desc_idx)
            elif tag == CONSTANT_InvokeDynamic:
                boot_idx = self._read_u2()
                nat_idx = self._read_u2()
                self.constant_pool[idx] = (tag, boot_idx, nat_idx)
            else:
                break
            idx += 1

        self.access_flags = self._read_u2()
        this_idx = self._read_u2()
        self.this_class = self.get_class_name(this_idx)
        super_idx = self._read_u2()
        self.super_class = self.get_class_name(super_idx) if super_idx != 0 else ""

        # Interfaces
        if_count = self._read_u2()
        for _ in range(if_count):
            self.interfaces.append(self.get_class_name(self._read_u2()))

        # Fields
        fields_count = self._read_u2()
        for _ in range(fields_count):
            f_flags = self._read_u2()
            f_name_idx = self._read_u2()
            f_desc_idx = self._read_u2()
            attrs = self._read_attributes()
            self.fields.append({
                "flags": f_flags,
                "name": self.get_utf8(f_name_idx),
                "descriptor": self.get_utf8(f_desc_idx),
                "attributes": attrs,
            })

        # Methods
        methods_count = self._read_u2()
        for _ in range(methods_count):
            m_flags = self._read_u2()
            m_name_idx = self._read_u2()
            m_desc_idx = self._read_u2()
            attrs = self._read_attributes()
            self.methods.append({
                "flags": m_flags,
                "name": self.get_utf8(m_name_idx),
                "descriptor": self.get_utf8(m_desc_idx),
                "attributes": attrs,
            })

    def _read_attributes(self) -> Dict[str, bytes]:
        attrs: Dict[str, bytes] = {}
        count = self._read_u2()
        for _ in range(count):
            name_idx = self._read_u2()
            attr_name = self.get_utf8(name_idx)
            length = self._read_u4()
            data = self._read_bytes(length)
            attrs[attr_name] = data
        return attrs

    def get_utf8(self, idx: int) -> str:
        if idx in self.constant_pool and self.constant_pool[idx][0] == CONSTANT_Utf8:
            return self.constant_pool[idx][1]
        return ""

    def get_class_name(self, idx: int) -> str:
        if idx in self.constant_pool and self.constant_pool[idx][0] == CONSTANT_Class:
            name_idx = self.constant_pool[idx][1]
            return self.get_utf8(name_idx).replace("/", ".")
        return ""

    def get_string(self, idx: int) -> str:
        if idx in self.constant_pool and self.constant_pool[idx][0] == CONSTANT_String:
            str_idx = self.constant_pool[idx][1]
            return self.get_utf8(str_idx)
        return ""

    def get_method_ref(self, idx: int) -> Tuple[str, str, str]:
        """Returns (class_name, method_name, descriptor)."""
        if idx in self.constant_pool:
            entry = self.constant_pool[idx]
            cls_name = self.get_class_name(entry[1])
            nat_entry = self.constant_pool.get(entry[2])
            if nat_entry and nat_entry[0] == CONSTANT_NameAndType:
                m_name = self.get_utf8(nat_entry[1])
                desc = self.get_utf8(nat_entry[2])
                return cls_name, m_name, desc
        return "", "", ""

    def get_field_ref(self, idx: int) -> Tuple[str, str, str]:
        """Returns (class_name, field_name, descriptor)."""
        return self.get_method_ref(idx)


class BytecodeDecompiler:
    """Decompiles parsed class file structures and opcodes into Java AST."""

    def __init__(self, reader: ClassFileReader) -> None:
        self.reader = reader

    def decompile(self) -> JavaCompilationUnit:
        class_name = self.reader.this_class.split(".")[-1]
        pkg_parts = self.reader.this_class.split(".")[:-1]
        pkg_decl = None
        if pkg_parts:
            from languages.java.ast_nodes import JavaPackageDeclaration
            pkg_decl = JavaPackageDeclaration(name=".".join(pkg_parts))

        # Modifiers
        mods: List[str] = []
        if self.reader.access_flags & ACC_PUBLIC:
            mods.append("public")
        if self.reader.access_flags & ACC_FINAL:
            mods.append("final")
        if self.reader.access_flags & ACC_ABSTRACT:
            mods.append("abstract")

        members: List[Any] = []

        # Decompile fields
        for f in self.reader.fields:
            f_mods: List[str] = []
            if f["flags"] & ACC_PUBLIC:
                f_mods.append("public")
            elif f["flags"] & ACC_PRIVATE:
                f_mods.append("private")
            elif f["flags"] & ACC_PROTECTED:
                f_mods.append("protected")
            if f["flags"] & ACC_STATIC:
                f_mods.append("static")
            if f["flags"] & ACC_FINAL:
                f_mods.append("final")

            f_type = self._descriptor_to_type(f["descriptor"])
            members.append(
                JavaFieldDeclaration(
                    modifiers=f_mods,
                    type_name=f_type,
                    name=f["name"],
                    initializer=None,
                )
            )

        # Decompile methods
        for m in self.reader.methods:
            m_decl = self._decompile_method(m)
            if m_decl:
                members.append(m_decl)

        cls_decl = JavaClassDeclaration(
            modifiers=mods,
            name=class_name,
            super_class=self.reader.super_class if self.reader.super_class != "java.lang.Object" else None,
            interfaces=self.reader.interfaces,
            members=members,
        )

        return JavaCompilationUnit(package=pkg_decl, imports=[], types=[cls_decl])

    def _decompile_method(self, m: Dict[str, Any]) -> Optional[JavaMethodDeclaration]:
        name = m["name"]
        if name == "<clinit>":
            # Static initializer block
            name = "static"

        m_mods: List[str] = []
        if m["flags"] & ACC_PUBLIC:
            m_mods.append("public")
        elif m["flags"] & ACC_PRIVATE:
            m_mods.append("private")
        elif m["flags"] & ACC_PROTECTED:
            m_mods.append("protected")
        if m["flags"] & ACC_STATIC:
            m_mods.append("static")
        if m["flags"] & ACC_FINAL:
            m_mods.append("final")

        ret_type, param_types = self._parse_method_descriptor(m["descriptor"])
        params: List[JavaParameter] = []
        for i, pt in enumerate(param_types):
            params.append(JavaParameter(type_name=pt, name=f"arg{i}"))

        body = None
        if "Code" in m["attributes"]:
            body = self._decompile_code(m["attributes"]["Code"])

        return JavaMethodDeclaration(
            modifiers=m_mods,
            return_type=ret_type,
            name=name,
            parameters=params,
            body=body,
        )

    def _decompile_code(self, code_attr: bytes) -> JavaBlock:
        """Simulates bytecode stack to reconstruct high-level statements."""
        if len(code_attr) < 8:
            return JavaBlock(statements=[])

        max_stack, max_locals, code_len = struct.unpack(">HHI", code_attr[:8])
        code = code_attr[8 : 8 + code_len]

        stack: List[JavaExpression] = []
        stmts: List[JavaStatement] = []
        locals_map: Dict[int, str] = {}
        var_counter = 1

        pos = 0
        while pos < len(code):
            opcode = code[pos]
            pos += 1

            # NOP
            if opcode == 0x00:
                continue

            # Constants: aconst_null, iconst_m1 .. iconst_5
            elif opcode == 0x01:  # aconst_null
                stack.append(JavaLiteral(value=None, raw="null", type_name="null"))
            elif 0x02 <= opcode <= 0x08:  # iconst_m1 .. iconst_5
                val = opcode - 0x03
                stack.append(JavaLiteral(value=val, raw=str(val), type_name="int"))

            # bipush, sipush
            elif opcode == 0x10:  # bipush
                byte_val = struct.unpack(">b", code[pos : pos + 1])[0]
                pos += 1
                stack.append(JavaLiteral(value=byte_val, raw=str(byte_val), type_name="int"))
            elif opcode == 0x11:  # sipush
                short_val = struct.unpack(">h", code[pos : pos + 2])[0]
                pos += 2
                stack.append(JavaLiteral(value=short_val, raw=str(short_val), type_name="int"))

            # ldc, ldc_w, ldc2_w
            elif opcode == 0x12:  # ldc
                cp_idx = code[pos]
                pos += 1
                stack.append(self._get_constant_literal(cp_idx))
            elif opcode in (0x13, 0x14):  # ldc_w, ldc2_w
                cp_idx = struct.unpack(">H", code[pos : pos + 2])[0]
                pos += 2
                stack.append(self._get_constant_literal(cp_idx))

            # Loads: iload, aload
            elif opcode in (0x15, 0x19):  # iload, aload
                idx = code[pos]
                pos += 1
                var_name = locals_map.get(idx, f"var{idx}")
                stack.append(JavaIdentifier(name=var_name))
            elif 0x1A <= opcode <= 0x1D:  # iload_0 .. iload_3
                idx = opcode - 0x1A
                var_name = locals_map.get(idx, f"var{idx}" if idx > 0 else "this")
                stack.append(JavaIdentifier(name=var_name))
            elif 0x2A <= opcode <= 0x2D:  # aload_0 .. aload_3
                idx = opcode - 0x2A
                var_name = locals_map.get(idx, f"var{idx}" if idx > 0 else "this")
                stack.append(JavaIdentifier(name=var_name))

            # Stores: istore, astore
            elif opcode in (0x36, 0x3A):  # istore, astore
                idx = code[pos]
                pos += 1
                val = stack.pop() if stack else JavaLiteral(value=0, raw="0")
                if idx not in locals_map:
                    locals_map[idx] = f"v{var_counter}"
                    var_counter += 1
                    stmts.append(JavaVariableDeclarationStatement(type_name="var", name=locals_map[idx], initializer=val))
                else:
                    stmts.append(JavaExpressionStatement(expression=JavaBinaryExpression(left=JavaIdentifier(name=locals_map[idx]), operator="=", right=val)))
            elif 0x3B <= opcode <= 0x3E:  # istore_0 .. istore_3
                idx = opcode - 0x3B
                val = stack.pop() if stack else JavaLiteral(value=0, raw="0")
                if idx not in locals_map:
                    locals_map[idx] = f"v{var_counter}"
                    var_counter += 1
                    stmts.append(JavaVariableDeclarationStatement(type_name="var", name=locals_map[idx], initializer=val))
                else:
                    stmts.append(JavaExpressionStatement(expression=JavaBinaryExpression(left=JavaIdentifier(name=locals_map[idx]), operator="=", right=val)))
            elif 0x4B <= opcode <= 0x4E:  # astore_0 .. astore_3
                idx = opcode - 0x4B
                val = stack.pop() if stack else JavaLiteral(value=None, raw="null")
                if idx not in locals_map:
                    locals_map[idx] = f"v{var_counter}"
                    var_counter += 1
                    stmts.append(JavaVariableDeclarationStatement(type_name="var", name=locals_map[idx], initializer=val))
                else:
                    stmts.append(JavaExpressionStatement(expression=JavaBinaryExpression(left=JavaIdentifier(name=locals_map[idx]), operator="=", right=val)))

            # Arithmetic ops: iadd, isub, imul, idiv, irem, ixor, iand, ior
            elif opcode in (0x60, 0x64, 0x68, 0x6C, 0x70, 0x7E, 0x80, 0x82):
                op_map = {
                    0x60: "+", 0x64: "-", 0x68: "*", 0x6C: "/",
                    0x70: "%", 0x7E: "&", 0x80: "|", 0x82: "^"
                }
                op = op_map[opcode]
                right = stack.pop() if stack else JavaLiteral(value=0, raw="0")
                left = stack.pop() if stack else JavaLiteral(value=0, raw="0")
                stack.append(JavaBinaryExpression(operator=op, left=left, right=right))

            # getstatic
            elif opcode == 0xB2:  # getstatic
                cp_idx = struct.unpack(">H", code[pos : pos + 2])[0]
                pos += 2
                cls_name, f_name, _ = self.reader.get_field_ref(cp_idx)
                short_cls = cls_name.split(".")[-1]
                stack.append(JavaFieldAccess(target=JavaIdentifier(name=short_cls), name=f_name))

            # invokevirtual, invokespecial, invokestatic
            elif opcode in (0xB6, 0xB7, 0xB8):
                cp_idx = struct.unpack(">H", code[pos : pos + 2])[0]
                pos += 2
                cls_name, m_name, desc = self.reader.get_method_ref(cp_idx)
                ret_t, p_types = self._parse_method_descriptor(desc)

                args = [stack.pop() for _ in range(min(len(p_types), len(stack)))][::-1]
                target = None
                if opcode in (0xB6, 0xB7):  # virtual or special call has target object
                    target = stack.pop() if stack else None
                else:
                    short_cls = cls_name.split(".")[-1]
                    target = JavaIdentifier(name=short_cls)

                call_expr = JavaMethodCall(target=target, name=m_name, arguments=args)
                if ret_t == "void":
                    stmts.append(JavaExpressionStatement(expression=call_expr))
                else:
                    stack.append(call_expr)

            # return, ireturn, areturn
            elif opcode == 0xB1:  # return
                stmts.append(JavaReturnStatement(expression=None))
            elif opcode in (0xAC, 0xB0):  # ireturn, areturn
                ret_val = stack.pop() if stack else None
                stmts.append(JavaReturnStatement(expression=ret_val))
            else:
                pass  # Safely step over unknown / complex bytecode

        # Any remaining expression on stack emitted as statement
        while stack:
            expr = stack.pop(0)
            if not isinstance(expr, JavaIdentifier) or expr.name != "this":
                stmts.append(JavaExpressionStatement(expression=expr))

        return JavaBlock(statements=stmts)

    def _get_constant_literal(self, cp_idx: int) -> JavaLiteral:
        if cp_idx in self.reader.constant_pool:
            tag, val = self.reader.constant_pool[cp_idx]
            if tag == CONSTANT_String:
                s = self.reader.get_string(cp_idx)
                return JavaLiteral(value=s, raw=repr(s), type_name="String")
            elif tag == CONSTANT_Integer:
                return JavaLiteral(value=val, raw=str(val), type_name="int")
            elif tag == CONSTANT_Long:
                return JavaLiteral(value=val, raw=f"{val}L", type_name="long")
            elif tag == CONSTANT_Float:
                return JavaLiteral(value=val, raw=f"{val}f", type_name="float")
            elif tag == CONSTANT_Double:
                return JavaLiteral(value=val, raw=str(val), type_name="double")
        return JavaLiteral(value=None, raw="null", type_name="null")

    def _descriptor_to_type(self, desc: str) -> str:
        if desc.startswith("L") and desc.endswith(";"):
            return desc[1:-1].replace("/", ".").split(".")[-1]
        type_map = {
            "B": "byte", "C": "char", "D": "double", "F": "float",
            "I": "int", "J": "long", "S": "short", "Z": "boolean", "V": "void"
        }
        if desc in type_map:
            return type_map[desc]
        if desc.startswith("["):
            return f"{self._descriptor_to_type(desc[1:])}[]"
        return "Object"

    def _parse_method_descriptor(self, desc: str) -> Tuple[str, List[str]]:
        """Parses (ILjava/lang/String;)V into ('void', ['int', 'String'])."""
        if not desc.startswith("("):
            return "void", []
        param_part, ret_part = desc[1:].split(")", 1)
        params: List[str] = []
        i = 0
        while i < len(param_part):
            ch = param_part[i]
            if ch == "L":
                end = param_part.find(";", i)
                params.append(self._descriptor_to_type(param_part[i : end + 1]))
                i = end + 1
            elif ch == "[":
                # Array type
                i += 1
                if param_part[i] == "L":
                    end = param_part.find(";", i)
                    params.append(f"{self._descriptor_to_type(param_part[i:end+1])}[]")
                    i = end + 1
                else:
                    params.append(f"{self._descriptor_to_type(param_part[i])}[]")
                    i += 1
            else:
                params.append(self._descriptor_to_type(ch))
                i += 1

        ret_type = self._descriptor_to_type(ret_part)
        return ret_type, params


def parse_class_or_jar(file_bytes: bytes, filename: Optional[str] = None) -> JavaCompilationUnit:
    """Reads either a .class file or .jar archive and decompiles it into a Java AST."""
    fname = filename or "<class>"
    if fname.endswith(".jar") or file_bytes.startswith(b"PK\x03\x04"):
        # ZIP/JAR archive: extract and decompile class files
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            class_names = [n for n in z.namelist() if n.endswith(".class") and not n.startswith("META-INF/")]
            all_types: List[Any] = []
            pkg_decl = None
            for cname in class_names:
                cdata = z.read(cname)
                reader = ClassFileReader(cdata, filename=cname)
                decompiler = BytecodeDecompiler(reader)
                unit = decompiler.decompile()
                if not pkg_decl and unit.package:
                    pkg_decl = unit.package
                all_types.extend(unit.types)
            return JavaCompilationUnit(package=pkg_decl, imports=[], types=all_types)

    # Standard single .class file
    reader = ClassFileReader(file_bytes, filename=filename)
    decompiler = BytecodeDecompiler(reader)
    return decompiler.decompile()
