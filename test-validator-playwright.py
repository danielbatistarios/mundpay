#!/usr/bin/env python3
"""
Teste: abre validator.schema.org, cola JSON-LD via CodeMirror API e lê o resultado.
"""

import json
from pathlib import Path
import extruct
from playwright.sync_api import sync_playwright

HTML_FILE = Path(__file__).parent / "preview/home.html"
VALIDATOR_URL = "https://validator.schema.org/"
SCREENSHOT_DIR = Path(__file__).parent

def extract_first_jsonld(html_path: Path) -> str:
    html = html_path.read_text(encoding="utf-8")
    data = extruct.extract(html, syntaxes=["json-ld"])
    blocks = data.get("json-ld", [])
    if not blocks:
        raise ValueError("Nenhum JSON-LD encontrado")
    return json.dumps(blocks[0], ensure_ascii=False, indent=2)

def run():
    print(f"Extraindo JSON-LD de {HTML_FILE.name}...")
    schema_text = extract_first_jsonld(HTML_FILE)
    print(f"  {len(schema_text)} chars, {schema_text.count(chr(10))+1} linhas")

    print("\nAbrindo validator.schema.org...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(VALIDATOR_URL, wait_until="networkidle", timeout=30000)

        # Inspeciona TODOS os CodeMirrors e suas tabs ANTES de clicar em qualquer coisa
        cm_info = page.evaluate("""() => {
            const cms = [...document.querySelectorAll('.CodeMirror')];
            return cms.map((div, i) => ({
                index: i,
                visible: div.offsetParent !== null,
                hasCM: !!div.CodeMirror,
                value: div.CodeMirror ? div.CodeMirror.getValue().substring(0, 50) : '',
                parentId: div.parentElement ? div.parentElement.id : '',
                parentClass: div.parentElement ? div.parentElement.className.substring(0, 80) : '',
                grandParentId: div.parentElement?.parentElement?.id || '',
                grandParentClass: div.parentElement?.parentElement?.className?.substring(0, 80) || ''
            }));
        }""")
        print("\nCodeMirrors encontrados:")
        for cm in cm_info:
            print(f"  [{cm['index']}] visible={cm['visible']} parentId={cm['parentId']!r} gpId={cm['grandParentId']!r}")
            print(f"        parentClass={cm['parentClass']!r}")

        # Clica na aba Snippet via JS
        page.evaluate("""() => {
            const tabs = [...document.querySelectorAll('[role="tab"], .mdl-tabs__tab, a, button')];
            const tab = tabs.find(t => t.innerText.includes('Snippet'));
            if (tab) tab.click();
        }""")
        page.wait_for_timeout(1000)

        # Verifica visibilidade após trocar aba
        cm_after = page.evaluate("""() => {
            const cms = [...document.querySelectorAll('.CodeMirror')];
            return cms.map((div, i) => ({
                index: i,
                visible: div.offsetParent !== null,
                parentId: div.parentElement ? div.parentElement.id : ''
            }));
        }""")
        print("\nCodeMirrors após trocar para Snippet:")
        for cm in cm_after:
            print(f"  [{cm['index']}] visible={cm['visible']} parentId={cm['parentId']!r}")

        # Seta no CodeMirror do tab Snippet (grandParentId = 'new-test-code-tab')
        result = page.evaluate(f"""() => {{
            const cms = [...document.querySelectorAll('.CodeMirror')];
            // Primeiro: tenta pelo grandParentId conhecido do Snippet tab
            for (let i = 0; i < cms.length; i++) {{
                const div = cms[i];
                const gpId = div.parentElement?.parentElement?.id || '';
                if (div.CodeMirror && gpId === 'new-test-code-tab') {{
                    div.CodeMirror.setValue({json.dumps(schema_text)});
                    div.CodeMirror.refresh();
                    const len = div.CodeMirror.getValue().length;
                    return 'CM[' + i + '] (new-test-code-tab) setValue OK — ' + len + ' chars';
                }}
            }}
            // Fallback: pega o último CodeMirror visível (Snippet fica depois do URL)
            let last = null, lastIdx = -1;
            for (let i = 0; i < cms.length; i++) {{
                if (cms[i].CodeMirror && cms[i].offsetParent !== null) {{
                    last = cms[i]; lastIdx = i;
                }}
            }}
            if (last) {{
                last.CodeMirror.setValue({json.dumps(schema_text)});
                last.CodeMirror.refresh();
                return 'CM[' + lastIdx + '] (fallback último visível) setValue OK — ' + last.CodeMirror.getValue().length + ' chars';
            }}
            return 'ERRO: nenhum CM disponível';
        }}""")
        print(f"\n  Editor: {result}")

        page.screenshot(path=str(SCREENSHOT_DIR / "debug-apos-setValue.png"))

        # Clica no botão Testar
        clicked = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button, a')];
            const btn = btns.find(b => b.innerText.trim() === 'Testar');
            if (btn) { btn.click(); return btn.innerText.trim(); }
            return 'não encontrado';
        }""")
        print(f"  Botão: '{clicked}'")

        print("  Aguardando resultado (15s)...")
        page.wait_for_timeout(15000)
        page.screenshot(path=str(SCREENSHOT_DIR / "step-resultado.png"))
        print("  Screenshot salvo")

        # Clica em cada card de tipo para expandir os detalhes
        page.evaluate("""() => {
            document.querySelectorAll('[class*="type-card"], [class*="result-card"], [class*="entity"], .feLNVc-r4nke-YPqjbf').forEach(el => {
                try { el.click(); } catch(e) {}
            });
        }""")
        page.wait_for_timeout(2000)

        # Captura HTML completo da área de resultados para inspeção
        result_html = page.evaluate("""() => {
            // Pega o conteúdo de texto de toda a metade direita
            const right = document.querySelector('[class*="result"], [class*="output"], [class*="panel"], .feLNVc-bN97Pc-j2fUBb')
                       || document.querySelector('body');
            return right ? right.innerText : '';
        }""")

        result_text = page.inner_text("body")
        browser.close()

    # Exibe resultado
    print("\n" + "="*60)
    print("RESULTADO DO VALIDATOR.SCHEMA.ORG — home.html")
    print("="*60)
    skip = {"Testar seus dados estruturados", "Buscar URL", "Snippet de código",
            "Cole seu código", "Fechar", "Testar", "Testar de novo", "search",
            "public", "Inserir um URL", "Snippet", "Ok", "Schema.org",
            "DocumentationSchemasValidateAbout", "VALIDAR", "language_japanese_kana",
            "info", "play_arrow", "あ", "ã"}
    lines = [l.strip() for l in result_text.split("\n") if l.strip()]
    seen, output = set(), []
    for line in lines:
        if line in seen or line in skip or len(line) < 3:
            continue
        seen.add(line)
        output.append(line)

    if output:
        for line in output[:100]:
            print(f"  {line}")
    else:
        print("  (sem resultado — veja step-resultado.png)")

if __name__ == "__main__":
    run()
