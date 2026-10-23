"""Research-only M1 package.

Research adapts typed strategies to the frozen M0 kernel and keeps immutable
experiment evidence. M0 core and future Production must never import this
namespace (enforced by ``boundaries.import_rules``).
"""
