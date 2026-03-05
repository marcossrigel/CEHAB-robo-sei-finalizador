from seleniumbase import SB
import os
import re
import gspread
from google.oauth2.service_account import Credentials

SHEET_URL = "https://docs.google.com/spreadsheets/d/1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM/edit"
SHEET_ID  = "1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM"
WORKSHEET_GID = 1189147903
CRED_JSON = r"formulariosolicitacaopagamento-6292734a5ede.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

SEI_LOGIN_URL = "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"

XP_USUARIO = '//*[@id="txtUsuario"]'
XP_SENHA = '//*[@id="pwdSenha"]'
CSS_SELECT_ORGAO = "#selOrgao"
CSS_BTN_ACESSAR = "#sbmAcessar"

XP_TXT_PESQUISA_RAPIDA = '//*[@id="txtPesquisaRapida"]'
XP_BTN_LUPA_PESQUISA = '//*[@id="spnInfraUnidade"]/img'  # lupa

def login_sei(sb: SB, orgao: str = "CEHAB") -> None:
    sei_user = os.getenv("SEI_USER", "marcos.rigel")
    sei_pass = os.getenv("SEI_PASS", "Abc123!@")

    sb.maximize_window()
    sb.open(SEI_LOGIN_URL)
    sb.wait_for_ready_state_complete()

    if sb.is_element_visible(XP_TXT_PESQUISA_RAPIDA):
        return

    sb.wait_for_element_visible(XP_USUARIO, timeout=30)
    sb.type(XP_USUARIO, sei_user)

    sb.wait_for_element_visible(XP_SENHA, timeout=30)
    sb.type(XP_SENHA, sei_pass)

    sb.wait_for_element_visible(CSS_SELECT_ORGAO, timeout=30)
    sb.select_option_by_text(CSS_SELECT_ORGAO, orgao)

    sb.wait_for_element_clickable(CSS_BTN_ACESSAR, timeout=30)
    try:
        sb.click(CSS_BTN_ACESSAR)
    except Exception:
        sb.js_click(CSS_BTN_ACESSAR)

    try:
        sb.accept_alert(timeout=2)
    except Exception:
        pass
    try:
        sb.switch_to_window(-1)
    except Exception:
        pass

    sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=60)

def _extract_sheet_id(url_or_id: str) -> str:
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url_or_id):
        return url_or_id
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url_or_id)
    if not m:
        raise ValueError("Não consegui extrair o SHEET_ID. Passe o ID puro ou a URL completa.")
    return m.group(1)

def _open_worksheet_by_gid(spreadsheet, gid: int):
    for ws in spreadsheet.worksheets():
        if getattr(ws, "id", None) == gid:
            return ws
    raise ValueError(f"Não encontrei worksheet com gid={gid}. Confira se esse gid é da aba certa.")

def read_sheet_rows(sheet_url_or_id: str, gid: int):
    creds = Credentials.from_service_account_file(CRED_JSON, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sheet_id = _extract_sheet_id(sheet_url_or_id)
    sh = gc.open_by_key(sheet_id)
    ws = _open_worksheet_by_gid(sh, gid)

    rows = ws.get_all_values()
    if not rows or len(rows) < 2:
        return ws.title, []

    header = [h.strip() for h in rows[0]]
    data = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        data.append({header[i]: r[i].strip() for i in range(len(header))})

    return ws.title, data

def normalize(s: str) -> str:
    return (s or "").strip().upper()


def listar_todos_os_arquivos_na_arvore(sb: SB, limite: int | None = None) -> list[str]:
    sb.wait_for_ready_state_complete()
    sb.sleep(1)

    els = sb.find_elements("//a")   # ✅ aqui é o ajuste

    itens = []
    for el in els:
        try:
            t = (el.text or "").strip()
            if t and len(t) >= 2:
                itens.append(t)
        except Exception:
            pass

    seen = set()
    out = []
    for t in itens:
        if t not in seen:
            seen.add(t)
            out.append(t)

    if limite is not None:
        return out[:limite]
    return out


def get_seis_enviados(dados: list[dict]) -> list[str]:
    if not dados:
        return []

    keys = list(dados[0].keys())

    def find_key(possiveis):
        for k in keys:
            nk = normalize(k)
            for p in possiveis:
                if nk == normalize(p):
                    return k
        return None

    key_sei = find_key(["N° do SEI", "Nº do SEI", "N DO SEI", "NUMERO DO SEI", "NÚMERO DO SEI"])
    key_status = find_key(["STATUS"])

    if not key_sei or not key_status:
        raise ValueError(f"Colunas não encontradas. Achei: {keys}")

    seis = []
    for row in dados:
        if normalize(row.get(key_status)) == "ENVIADO":
            sei = (row.get(key_sei) or "").strip()
            if sei:
                seis.append(sei)

    # remove duplicados mantendo ordem
    seen = set()
    out = []
    for s in seis:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def esperar_sumir_aguarde(sb: SB, timeout: int = 20):
    """
    Espera o SEI terminar de carregar a árvore (quando aparece 'Aguarde...').
    """
    for _ in range(timeout * 2):  # checa a cada 0.5s
        try:
            if not sb.is_text_visible("Aguarde"):
                return
        except Exception:
            pass
        sb.sleep(0.5)


def abrir_todas_as_pastas(sb: SB, limite: int = 10):
    for i in range(1, limite + 1):
        xp = f"//*[@id='joinPASTA{i}']"
        try:
            if sb.is_element_present(xp):
                sb.js_click(xp)
                print(f"📂 Clique na Pasta {i}")
                esperar_sumir_aguarde(sb, timeout=20)
                sb.sleep(0.3)
        except Exception:
            pass

# =========================
# 1) PESQUISAR UM SEI
# =========================
def pesquisar_sei(sb: SB, sei: str) -> None:
    sb.wait_for_element_visible(XP_TXT_PESQUISA_RAPIDA, timeout=30)
    sb.click(XP_TXT_PESQUISA_RAPIDA)
    sb.clear(XP_TXT_PESQUISA_RAPIDA)
    sb.type(XP_TXT_PESQUISA_RAPIDA, sei)

    sb.wait_for_element_clickable(XP_BTN_LUPA_PESQUISA, timeout=30)
    try:
        sb.click(XP_BTN_LUPA_PESQUISA)
    except Exception:
        sb.js_click(XP_BTN_LUPA_PESQUISA)

    sb.wait_for_ready_state_complete()
    sb.sleep(1.2)  # dá tempo da árvore renderizar

# =========================
# 2) PEGAR ÚLTIMA "NOTA FISCAL" DA ÁRVORE
def buscar_ultima_nota_fiscal(sb: SB) -> str | None:
    """
    Procura na árvore do SEI qualquer item contendo 'Nota Fiscal'
    e retorna o último encontrado.
    """

    xp_notas = "//a[contains(translate(normalize-space(.),'abcdefghijklmnopqrstuvwxyzáàâãäéèêëíìîïóòôõöúùûüç','ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ'),'NOTA FISCAL')]"

    sb.wait_for_ready_state_complete()
    sb.sleep(2)

    try:
        elementos = sb.find_elements(xp_notas)
    except Exception:
        elementos = []

    notas = []
    for el in elementos:
        try:
            texto = el.text.strip()
            if "NOTA FISCAL" in texto.upper():
                notas.append(texto)
        except:
            pass

    if not notas:
        return None

    return notas[-1]


# ========= ÁRVORE / PASTAS =========

def switch_to_arvore(sb: SB) -> None:
    """
    No SEI, a árvore geralmente fica em um iframe (comum: 'ifrArvore').
    Tenta trocar automaticamente para o frame certo.
    """
    sb.switch_to_default_content()

    # tenta nomes comuns do SEI
    for name in ["ifrArvore", "ifrArvoreHtml", "ifrArvoreVisualizacao", "ifrArvoreProcesso"]:
        try:
            sb.switch_to_frame(name)
            return
        except Exception:
            pass

    frames = sb.find_elements("xpath=//iframe")
    for fr in frames:
        try:
            sb.switch_to_default_content()
            sb.switch_to_frame(fr)
            if sb.is_element_present("xpath=//a") and (sb.is_text_visible("I") or sb.is_text_visible("II")):
                return
        except Exception:
            pass

    sb.switch_to_default_content()
    raise RuntimeError("Não consegui localizar o iframe da árvore (ifrArvore).")


def expandir_toda_arvore(sb: SB, max_passes: int = 25) -> None:

    xp_expand = (
        "//img["
        "contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expandir')"
        " or contains(translate(@alt,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expandir')"
        " or contains(@src,'mais') or contains(@src,'plus') or contains(@src,'expand')"
        "]"
    )

    for _ in range(max_passes):
        sb.wait_for_ready_state_complete()
        sb.sleep(0.4)

        try:
            buttons = sb.find_elements(f"xpath={xp_expand}")
        except Exception:
            buttons = []

        if not buttons:
            break

        clicked_any = False
        for b in buttons[:40]:
            try:
                sb.js_click(b)
                clicked_any = True
                sb.sleep(0.15)
            except Exception:
                pass

        if not clicked_any:
            break


if __name__ == "__main__":
    aba, dados = read_sheet_rows(SHEET_ID, WORKSHEET_GID)
    print(f"✅ Aba lida: {aba}")
    print(f"✅ Linhas de dados: {len(dados)}")

    seis_enviados = get_seis_enviados(dados)
    print(f"📌 SEIs com STATUS=ENVIADO: {len(seis_enviados)}")

    if not seis_enviados:
        raise SystemExit("Sem SEIs com STATUS=ENVIADO.")

    sei_teste = seis_enviados[0]
    print("🧪 SEI de teste:", sei_teste)

    with SB(uc=False, headless=False, test=False) as sb:
        login_sei(sb, orgao="CEHAB")
        print("✅ Logado no SEI com sucesso!")

        # 1) pesquisa o SEI
        pesquisar_sei(sb, sei_teste)

        # 2) vai pra árvore (iframe)
        switch_to_arvore(sb)

        # 3) abre pastas I, II, III...
        abrir_todas_as_pastas(sb, limite=10)

        # 4) garante que acabou "Aguarde..."
        esperar_sumir_aguarde(sb, timeout=20)
        sb.sleep(0.5)

        # ====== (A) LISTAR TUDO (debug) ======
        arquivos = listar_todos_os_arquivos_na_arvore(sb)
        print(f"📄 Itens encontrados na árvore: {len(arquivos)}")
        for a in arquivos:
            print(" -", a)

        # ====== (B) PEGAR ÚLTIMA NOTA FISCAL ======
        nota = buscar_ultima_nota_fiscal(sb)
        print("🧾 Última Nota Fiscal encontrada:", nota)
        print("📌 Resultado final:", {sei_teste: nota})

        # volta pro conteúdo padrão
        sb.switch_to_default_content()

        input("ENTER para fechar...")
