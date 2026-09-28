"""Language subsystem and base interfaces."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from core.exceptions import UnsupportedLanguageError


class BaseLanguage(ABC):
    """Abstract interface that each supported language must implement."""

    name: str = "base"
    extensions: List[str] = []

    @abstractmethod
    def parse(self, source: str, filename: Optional[str] = None) -> Any:
        """Parse source string into AST representation."""
        pass

    @abstractmethod
    def unparse(self, ast_tree: Any) -> str:
        """Regenerate source string from AST representation."""
        pass

    def to_ir(self, ast_tree: Any) -> Any:
        """Convert language AST into Common IRModule."""
        raise NotImplementedError(f"IR conversion not implemented for {self.name}")

    def from_ir(self, ir_module: Any) -> Any:
        """Convert Common IRModule back into language AST."""
        raise NotImplementedError(f"Reverse IR conversion not implemented for {self.name}")


class LanguageRegistry:
    """Registry of supported programming languages."""

    def __init__(self) -> None:
        self._by_name: Dict[str, BaseLanguage] = {}
        self._by_ext: Dict[str, BaseLanguage] = {}

    def register(self, language: BaseLanguage) -> None:
        self._by_name[language.name.lower()] = language
        for ext in language.extensions:
            self._by_ext[ext.lower()] = language

    def get(self, name_or_ext: str) -> BaseLanguage:
        target = name_or_ext.lower()
        if target in self._by_name:
            return self._by_name[target]
        if target in self._by_ext:
            return self._by_ext[target]
        if not target.startswith(".") and f".{target}" in self._by_ext:
            return self._by_ext[f".{target}"]
        raise UnsupportedLanguageError(f"Unsupported language or extension: '{name_or_ext}'")

    def detect_language(self, filename: str) -> Optional[BaseLanguage]:
        for ext, lang in self._by_ext.items():
            if filename.lower().endswith(ext):
                return lang
        return None

    @property
    def supported_languages(self) -> List[str]:
        return list(self._by_name.keys())


registry = LanguageRegistry()
