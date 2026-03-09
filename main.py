from seleniumbase import SB
import os
import re
import glob
import time
import gspread
from google.oauth2.service_account import Credentials
from selenium.common.exceptions import InvalidSessionIdException
import json
from datetime import datetime

SHEET_URL = "https://docs.google.com/spreadsheets/d/1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM/edit"
SHEET_ID  = "1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM"
WORKSHEET_GID = 1189147903
CRED_JSON = r"formulariosolicitacaopagamento-6292734a5ede.json"
JSON_PATH = "ultimas_notas.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

SEI_LOGIN_URL = "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"

XP_USUARIO = '//*[@id="txtUsuario"]'
XP_SENHA = '//*[@id="pwdSenha"]'
CSS_SELECT_ORGAO = "#selOrgao"
CSS_BTN_ACESSAR = "#sbmAcessar"
BAIXAR_PDF = False

XP_TXT_PESQUISA_RAPIDA = '//*[@id="txtPesquisaRapida"]'
XP_BTN_LUPA_PESQUISA = '//*[@id="spnInfraUnidade"]/img'

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


def _sanitize_filename(s: str) -> str:
    # troca caracteres ruins pra nome de arquivo
    return re.sub(r'[\\/:*?"<>|]+', "_", s)

def baixar_pdf_visualizador(sb: SB, pasta="notas_fiscais", nome="nota.pdf", timeout=60):
    os.makedirs(pasta, exist_ok=True)

    handles_antes = sb.driver.window_handles
    sb.sleep(2)

    handles_depois = sb.driver.window_handles
    if len(handles_depois) > len(handles_antes):
        sb.switch_to_window(-1)
        sb.sleep(1)

    sb.switch_to_default_content()
    iframe_encontrado = False

    for fr in sb.find_elements("xpath=//iframe"):
        try:
            sb.switch_to_default_content()
            sb.switch_to_frame(fr)
            if sb.is_element_present('xpath=//*[@id="icon"]/cr-icon'):
                iframe_encontrado = True
                break
        except Exception:
            pass

    if not iframe_encontrado:
        sb.switch_to_default_content()

    XP_DOWNLOAD = '//*[@id="icon"]/cr-icon'
    sb.wait_for_element_clickable(XP_DOWNLOAD, timeout=20)
    sb.js_click(XP_DOWNLOAD)

    t0 = time.time()
    while time.time() - t0 < timeout:
        cr = glob.glob(os.path.join(pasta, "*.crdownload"))
        if not cr:
            time.sleep(1)
            pdfs = glob.glob(os.path.join(pasta, "*.pdf"))
            if pdfs:
                break
        time.sleep(0.5)

    pdfs = glob.glob(os.path.join(pasta, "*.pdf"))
    if not pdfs:
        raise RuntimeError("Download não apareceu na pasta (nenhum .pdf encontrado).")

    ultimo = max(pdfs, key=os.path.getmtime)
    destino = os.path.join(pasta, _sanitize_filename(nome))

    if os.path.exists(destino):
        os.remove(destino)

    os.rename(ultimo, destino)

    try:
        if len(sb.driver.window_handles) > 1:
            sb.close_current_window()
            sb.switch_to_window(0)
    except Exception:
        pass

    sb.switch_to_default_content()


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

    seen = set()
    out = []
    for s in seis:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def esperar_sumir_aguarde(sb: SB, timeout: int = 20):
    for _ in range(timeout * 2):
        try:
            if not sb.is_text_visible("Aguarde"):
                return
        except Exception:
            pass
        sb.sleep(0.5)

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
    sb.sleep(1.2)

def switch_to_arvore(sb: SB) -> None:

    sb.switch_to_default_content()

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


def detectar_pastas(sb: SB) -> list[int]:
    els = sb.find_elements("//a[starts-with(@id,'joinPASTA')] | //* [starts-with(@id,'joinPASTA')]")
    nums = []
    for el in els:
        try:
            _id = el.get_attribute("id") or ""
            m = re.match(r"joinPASTA(\d+)", _id)
            if m:
                nums.append(int(m.group(1)))
        except Exception:
            pass

    nums = sorted(set(nums))
    return nums

def coletar_itens_visiveis(sb: SB) -> list[str]:
    els = sb.find_elements("//a")
    itens = []
    for el in els:
        try:
            t = (el.text or "").strip()
            if not t:
                continue
            if t.lower() == "aguarde...":
                continue
            if len(t) < 2:
                continue
            itens.append(t)
        except Exception:
            pass
    seen = set()
    out = []
    for t in itens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def abrir_pasta_e_pegar_itens(sb: SB, pasta_num: int) -> list[str]:

    def snap():
        esperar_sumir_aguarde(sb, timeout=30)
        sb.sleep(0.4)
        return coletar_itens_visiveis(sb)

    xp = f"//*[@id='joinPASTA{pasta_num}']"
    if not sb.is_element_present(xp):
        return []

    antes_lista = snap()
    antes_set = set(antes_lista)

    try:
        sb.js_click(xp)
    except Exception:
        sb.click(xp)

    depois1_lista = snap()
    depois1_set = set(depois1_lista)

    if len(depois1_set) < len(antes_set):
        fechado_lista = depois1_lista
        fechado_set = depois1_set

        try:
            sb.js_click(xp)
        except Exception:
            sb.click(xp)

        depois2_lista = snap()
        depois2_set = set(depois2_lista)

        diff = depois2_set - fechado_set
        itens = [t for t in depois2_lista if t in diff]
        return itens

    diff = depois1_set - antes_set
    itens = [t for t in depois1_lista if t in diff]
    return itens

def carregar_json(path: str) -> dict[str, str | None]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): (v if (v is None or isinstance(v, str)) else str(v)) for k, v in data.items()}
        return {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def salvar_json(path: str, data: dict[str, str | None]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_nota_fiscal(texto: str) -> bool:
    t = (texto or "").strip().upper()
    return t.startswith("NOTA FISCAL")

if __name__ == "__main__":
    aba, dados = read_sheet_rows(SHEET_ID, WORKSHEET_GID)

    seis_enviados = get_seis_enviados(dados)
    if not seis_enviados:
        raise SystemExit("Sem SEIs com STATUS=ENVIADO.")

    old_map = carregar_json(JSON_PATH)
    results_map: dict[str, str | None] = {}
    mudancas: list[tuple[str, str | None, str | None]] = []

    with SB(
        uc=False,
        headless=False,
        test=False
    ) as sb:
        login_sei(sb, orgao="CEHAB")

        for sei in seis_enviados:
            try:
                print(f"\nSEI: {sei}")

                sb.switch_to_default_content()
                pesquisar_sei(sb, sei)

                switch_to_arvore(sb)
                esperar_sumir_aguarde(sb, timeout=30)
                sb.sleep(0.4)

                pastas = detectar_pastas(sb)
                ultima_nota = None

                for p in pastas:
                    print(f"   Pasta {p}")
                    switch_to_arvore(sb)
                    itens = abrir_pasta_e_pegar_itens(sb, p)

                    for item in itens:
                        if is_nota_fiscal(item):
                            ultima_nota = item

                    sb.sleep(0.2)

                print(f" -> Última nota encontrada: {ultima_nota}")
                old_val = old_map.get(sei)
                results_map[sei] = ultima_nota

                if ultima_nota is not None and old_val != ultima_nota:
                    print("7. Documento mudou")

                    if BAIXAR_PDF:
                        print("8. Abrindo documento")
                        switch_to_arvore(sb)
                        xp_doc = f"//a[contains(normalize-space(), '{ultima_nota}')]"
                        sb.wait_for_element_clickable(xp_doc, timeout=20)
                        try:
                            sb.click(xp_doc)
                        except Exception:
                            sb.js_click(xp_doc)

                        sb.sleep(2)

                        print("9. Baixando PDF")
                        baixar_pdf_visualizador(
                            sb,
                            pasta="notas_fiscais",
                            nome=f"{sei.replace('/', '_')}.pdf"
                        )
                        print("10. PDF baixado com sucesso")

                    mudancas.append((sei, old_val, ultima_nota))

            except InvalidSessionIdException as e:
                print(f"\n[ERRO FATAL] SEI: {sei}")
                print(f"Tipo: {type(e).__name__}")
                print(f"Mensagem: {e}")
                results_map[sei] = old_map.get(sei)
                break

            except Exception as e:
                print(f"\n[ERRO] SEI: {sei}")
                print(f"Tipo: {type(e).__name__}")
                print(f"Mensagem: {e}")
                results_map[sei] = old_map.get(sei)

    salvar_json(JSON_PATH, results_map)

    for sei, old_val, new_val in mudancas:
        print(f"{sei} : {new_val}")

    print(f"\nAtualizações encontradas: {len(mudancas)}")
    print("Atualizado em:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    input("ENTER para fechar...")
