
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


if __name__ == "__main__":
    aba, dados = read_sheet_rows(SHEET_ID, WORKSHEET_GID)
    print(f"✅ Aba lida: {aba}")
    print(f"✅ Linhas de dados: {len(dados)}")

    seis_enviados = get_seis_enviados(dados)
    print(f"📌 SEIs com STATUS=ENVIADO: {len(seis_enviados)}")

    for sei in seis_enviados:
        print(" -", sei)

    with SB(uc=False, headless=False, test=False) as sb:
        login_sei(sb, orgao="CEHAB")
        print("✅ Logado no SEI com sucesso!")

        input("ENTER para fechar...")
