#!/usr/bin/env python3
"""
validate-schemas.py — Validador local de Schema JSON-LD
Uso: python3 validate-schemas.py [arquivo.html ...]

Sem argumentos: valida todos os arquivos em PAGES.
Com argumentos: valida apenas os arquivos especificados.

Camadas de validação:
  1. Extração via extruct (lê JSON-LD do HTML)
  2. Expansão via PyLD (valida sintaxe JSON-LD W3C)
  3. Regras semânticas (campos obrigatórios/recomendados por @type)
"""

import sys
import json
import os
from pathlib import Path

try:
    import extruct
    from pyld import jsonld
except ImportError as e:
    print(f"Dependência faltando: {e}")
    print("Instale com: pip3 install extruct PyLD --break-system-packages")
    sys.exit(1)

# ── Configuração ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent

PAGES = [
    "preview/home.html",
    "preview/pagamentos-e-taxas.html",
    "preview/apresentacao.html",
    "preview/me-ajuda.html",
    "preview/blog.html",
]

# Campos obrigatórios por @type (ausência = ERRO)
REQUIRED = {
    "Organization":     ["name", "url"],
    "FinancialService": ["name", "url"],
    "WebSite":          ["name", "url", "publisher"],
    "WebPage":          ["name", "publisher", "isPartOf"],
    "AboutPage":        ["name", "publisher", "mainEntity"],
    "FAQPage":          ["mainEntity"],
    "Person":           ["name"],
    "AggregateRating":  ["ratingValue", "bestRating"],
    "Offer":            ["price", "priceCurrency"],
    "UnitPriceSpecification": ["price", "priceCurrency"],
    "Question":         ["name", "acceptedAnswer"],
    "Answer":           ["text"],
    "BreadcrumbList":   ["itemListElement"],
    "SoftwareApplication": ["name", "applicationCategory"],
}

# Campos recomendados por @type (ausência = WARN)
RECOMMENDED = {
    "Organization": ["telephone", "logo", "address", "sameAs", "aggregateRating",
                     "contactPoint", "foundingDate"],
    "FinancialService": ["acceptedPaymentMethod", "currenciesAccepted",
                         "feesAndCommissionsSpecification"],
    "WebPage":      ["description", "dateModified", "speakableSpecification"],
    "AboutPage":    ["description", "dateModified"],
    "FAQPage":      ["about", "isPartOf"],
    "Person":       ["jobTitle", "image", "sameAs", "worksFor"],
    "AggregateRating": ["ratingCount", "reviewCount"],
    "Question":     [],
    "Organization": ["award"],
}

# ── Cores ANSI ───────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    return f"  {GREEN}[OK]{RESET}   {msg}"
def warn(msg):  return f"  {YELLOW}[WARN]{RESET} {msg}"
def err(msg):   return f"  {RED}[ERRO]{RESET} {msg}"
def info(msg):  return f"  {CYAN}[INFO]{RESET} {msg}"


# ── Extração ─────────────────────────────────────────────────────────────────

def extract_jsonld(html_path: Path) -> list[dict]:
    html = html_path.read_text(encoding="utf-8")
    base_url = html_path.as_uri()
    data = extruct.extract(html, base_url=base_url, syntaxes=["json-ld"])
    return data.get("json-ld", [])


# ── Flatten @graph ────────────────────────────────────────────────────────────

def flatten_graph(blocks: list[dict]) -> list[dict]:
    nodes = []
    for block in blocks:
        if "@graph" in block:
            nodes.extend(block["@graph"])
        else:
            nodes.append(block)
    return nodes


# ── Validação sintática (PyLD) ────────────────────────────────────────────────

def validate_pyld(blocks: list[dict]) -> list[str]:
    errors = []
    for i, block in enumerate(blocks):
        try:
            jsonld.expand(block)
        except Exception as e:
            msg = str(e)
            errors.append(f"Bloco {i+1}: erro de expansão PyLD — {msg[:120]}")
    return errors


# ── @id duplicados ────────────────────────────────────────────────────────────

def check_duplicate_ids(nodes: list[dict]) -> list[str]:
    seen = {}
    errors = []
    for node in nodes:
        node_id = node.get("@id")
        if node_id:
            if node_id in seen:
                errors.append(f'@id duplicado: "{node_id}"')
            seen[node_id] = True
    return errors


# ── Extrai @type como lista normalizada ───────────────────────────────────────

def get_types(node: dict) -> list[str]:
    raw = node.get("@type", [])
    if isinstance(raw, str):
        return [raw]
    return raw


# ── Normaliza chave (remove prefixo de namespace se presente) ─────────────────

def has_field(node: dict, field: str) -> bool:
    if field in node:
        val = node[field]
        if val is None:
            return False
        if isinstance(val, (list, dict)) and not val:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        return True
    return False


# ── Validação de FAQPage ──────────────────────────────────────────────────────

def validate_faqpage(node: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    main_entity = node.get("mainEntity", [])
    if isinstance(main_entity, dict):
        main_entity = [main_entity]

    if not main_entity:
        errors.append("FAQPage: mainEntity vazio ou ausente")
        return errors, warnings

    if len(main_entity) < 2:
        warnings.append(f"FAQPage: apenas {len(main_entity)} pergunta(s) — Google recomenda mínimo 2")

    for i, q in enumerate(main_entity, 1):
        q_type = get_types(q)
        if "Question" not in q_type:
            errors.append(f"FAQPage: item {i} não é @type Question (é {q_type})")
            continue

        if not has_field(q, "name"):
            errors.append(f"FAQPage: Question {i} sem campo 'name'")

        answer = q.get("acceptedAnswer")
        if not answer:
            errors.append(f"FAQPage: Question {i} sem 'acceptedAnswer'")
        elif isinstance(answer, dict):
            if not has_field(answer, "text"):
                errors.append(f"FAQPage: Question {i} — acceptedAnswer sem 'text'")
            text = answer.get("text", "")
            if isinstance(text, str) and len(text) < 20:
                warnings.append(f"FAQPage: Question {i} — texto da resposta muito curto ({len(text)} chars)")

    return errors, warnings


# ── Validação de AggregateRating ──────────────────────────────────────────────

def validate_aggregate_rating(node: dict, parent_type: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    rating_value = node.get("ratingValue")
    if rating_value is not None:
        try:
            rv = float(str(rating_value))
            if rv < 0:
                errors.append(f"AggregateRating em {parent_type}: ratingValue negativo ({rv})")
        except ValueError:
            errors.append(f"AggregateRating em {parent_type}: ratingValue não é numérico ({rating_value!r})")

    count = node.get("ratingCount") or node.get("reviewCount")
    if count is None:
        warnings.append(f"AggregateRating em {parent_type}: sem ratingCount nem reviewCount")
    else:
        try:
            if int(str(count)) < 1:
                errors.append(f"AggregateRating em {parent_type}: contagem de avaliações < 1")
        except ValueError:
            errors.append(f"AggregateRating em {parent_type}: ratingCount não é inteiro ({count!r})")

    return errors, warnings


# ── Validação semântica principal ─────────────────────────────────────────────

def validate_semantic(nodes: list[dict]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    for node in nodes:
        types = get_types(node)
        node_id = node.get("@id", "(sem @id)")
        label = f"{'+'.join(types)} {node_id}"

        for t in types:
            # Campos obrigatórios
            for field in REQUIRED.get(t, []):
                # Offer pode usar priceSpecification (UnitPriceSpecification) em vez de price/priceCurrency direto
                if field in ("price", "priceCurrency") and "Offer" in types:
                    if has_field(node, "priceSpecification"):
                        continue
                if not has_field(node, field):
                    errors.append(f"{label}: campo obrigatório '{field}' ausente")

            # Campos recomendados
            for field in RECOMMENDED.get(t, []):
                if not has_field(node, field):
                    warnings.append(f"{label}: campo recomendado '{field}' ausente")

        # Regras específicas por tipo
        if "FAQPage" in types:
            e, w = validate_faqpage(node)
            errors.extend(e)
            warnings.extend(w)

        if "AggregateRating" in types:
            e, w = validate_aggregate_rating(node, label)
            errors.extend(e)
            warnings.extend(w)

        # AggregateRating embutido em Organization
        if "Organization" in types and has_field(node, "aggregateRating"):
            ar = node["aggregateRating"]
            if isinstance(ar, dict):
                e, w = validate_aggregate_rating(ar, label)
                errors.extend(e)
                warnings.extend(w)

        # @context no nó raiz deve existir
        if "@context" not in node and "@graph" not in node:
            pass  # nós dentro de @graph não precisam de @context próprio

    return errors, warnings


# ── Relatório por página ──────────────────────────────────────────────────────

def report_page(html_path: Path) -> tuple[int, int]:
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}  {html_path.name}{RESET}")
    print(f"{CYAN}{'─'*60}{RESET}")

    if not html_path.exists():
        print(err(f"Arquivo não encontrado: {html_path}"))
        return 1, 0

    # Camada 1: extração
    try:
        blocks = extract_jsonld(html_path)
    except Exception as e:
        print(err(f"Falha ao extrair JSON-LD: {e}"))
        return 1, 0

    if not blocks:
        print(err("Nenhum bloco JSON-LD encontrado no HTML"))
        return 1, 0

    nodes = flatten_graph(blocks)
    has_graph = any("@graph" in b for b in blocks)
    graph_label = f"@graph com {len(nodes)} nós" if has_graph else f"{len(nodes)} nó(s) raiz"
    print(info(f"JSON-LD extraído: {len(blocks)} bloco(s) — {graph_label}"))

    total_errors, total_warnings = 0, 0

    # Camada 2: validação sintática PyLD
    pyld_errors = validate_pyld(blocks)
    if pyld_errors:
        for e in pyld_errors:
            print(err(e))
        total_errors += len(pyld_errors)
    else:
        print(ok("Expansão PyLD sem erros de sintaxe"))

    # @id duplicados
    dup_errors = check_duplicate_ids(nodes)
    if dup_errors:
        for e in dup_errors:
            print(err(e))
        total_errors += len(dup_errors)
    else:
        print(ok("Sem @id duplicados"))

    # Camada 3: validação semântica
    sem_errors, sem_warnings = validate_semantic(nodes)

    for e in sem_errors:
        print(err(e))
    for w in sem_warnings:
        print(warn(w))

    total_errors += len(sem_errors)
    total_warnings += len(sem_warnings)

    # Resumo da página
    if total_errors == 0 and total_warnings == 0:
        print(f"\n  {GREEN}{BOLD}✓ Página OK — sem erros nem avisos{RESET}")
    elif total_errors == 0:
        print(f"\n  {YELLOW}{BOLD}✓ Sem erros — {total_warnings} aviso(s){RESET}")
    else:
        print(f"\n  {RED}{BOLD}✗ {total_errors} erro(s), {total_warnings} aviso(s){RESET}")

    return total_errors, total_warnings


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        pages = [Path(p) for p in sys.argv[1:]]
    else:
        pages = [SCRIPT_DIR / p for p in PAGES]

    print(f"\n{BOLD}{'='*60}")
    print("  MUNDPAY — Validador de Schema JSON-LD")
    print(f"{'='*60}{RESET}")
    print(f"  Validando {len(pages)} página(s)...\n")

    total_errors = 0
    total_warnings = 0

    for page in pages:
        e, w = report_page(Path(page))
        total_errors += e
        total_warnings += w

    # Resumo final
    print(f"\n{BOLD}{'='*60}")
    print("  RESUMO FINAL")
    print(f"{'='*60}{RESET}")
    print(f"  Páginas analisadas : {len(pages)}")

    if total_errors == 0:
        print(f"  Erros              : {GREEN}{BOLD}0{RESET}")
    else:
        print(f"  Erros              : {RED}{BOLD}{total_errors}{RESET}")

    if total_warnings == 0:
        print(f"  Avisos             : {GREEN}0{RESET}")
    else:
        print(f"  Avisos             : {YELLOW}{total_warnings}{RESET}")

    print()

    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
