from oauth2client.service_account import ServiceAccountCredentials
import gspread
from getpass import getpass
import time

from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

CAMINHO_CREDENCIAL = "formulariosolicitacaopagamento-6292734a5ede.json"
PLANILHA_ID = "1lkM9yOjhu_D2nQjRFl-Wt6lNgWPvzl2wbQiaO633-KM"
GID_BMS_2026 = 1189147903

STATUS_ALVO = "ENVIADO"
SETOR_ALVO = "GAC"

SEI_URL = "https://sei.pe.gov.br/sip/login.php?sigla_orgao_sistema=GOVPE&sigla_sistema=SEI"
SEI_USUARIO = "marcos.rigel"
SEI_SENHA = "Abc123!@"
SEI_UNIDADE = "CEHAB"

def norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def conectar_google_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(CAMINHO_CREDENCIAL, scopes)
    return gspread.authorize(creds)

def achar_coluna(headers: list[str], *possiveis: str) -> int:
    h_norm = [norm(h) for h in headers]
    for nome in possiveis:
        n = norm(nome)
        if n in h_norm:
            return h_norm.index(n)
    raise KeyError(f"Coluna não encontrada. Tentei {possiveis}. Headers vistos: {headers}")

def ler_seis_enviado_gac(ws):
    valores = ws.get_all_values()
    if not valores or len(valores) < 2:
        return []

    headers = valores[0]
    idx_status = achar_coluna(headers, "STATUS", "Status")
    idx_setor_atual = achar_coluna(headers, "SETOR ATUAL", "Setor atual", "Setor")
    idx_sei = achar_coluna(headers, "N° do SEI", "Nº do SEI", "N° SEI", "Nº SEI", "SEI")

    seis = []
    vistos = set()

    for linha_idx, row in enumerate(valores[1:], start=2):
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        status = (row[idx_status] or "").strip().upper()
        setor_atual = (row[idx_setor_atual] or "").strip().upper()
        sei = (row[idx_sei] or "").strip()

        if status == STATUS_ALVO and setor_atual == SETOR_ALVO and sei:
            chave = norm(sei)
            if chave in vistos:
                continue
            vistos.add(chave)
            seis.append({"linha": linha_idx, "sei": sei})

    return seis

def acessar_sei_login(driver: Driver, usuario: str, senha: str, unidade: str = "CEHAB"):
    wait = WebDriverWait(driver, 30)
    driver.get(SEI_URL)

    def first_present(*locators):
        last = None
        for how, what in locators:
            try:
                return wait.until(EC.presence_of_element_located((how, what)))
            except Exception as e:
                last = e
        raise last

    def first_clickable(*locators):
        last = None
        for how, what in locators:
            try:
                return wait.until(EC.element_to_be_clickable((how, what)))
            except Exception as e:
                last = e
        raise last

    el_user = first_present(
        (By.ID, "txtUsuario"),
        (By.NAME, "txtUsuario"),
        (By.CSS_SELECTOR, "input#txtUsuario"),
    )
    el_user.clear()
    el_user.send_keys(usuario)

    el_pass = first_present(
        (By.ID, "pwdSenha"),
        (By.ID, "txtSenha"),
        (By.NAME, "pwdSenha"),
        (By.NAME, "txtSenha"),
        (By.CSS_SELECTOR, "input[type='password']"),
    )
    el_pass.clear()
    el_pass.send_keys(senha)

    try:
        el_sel = first_present(
            (By.ID, "selOrgao"),
            (By.NAME, "selOrgao"),
            (By.CSS_SELECTOR, "select#selOrgao"),
        )
        Select(el_sel).select_by_visible_text(unidade)
    except Exception:
        pass

    btn = first_clickable(
        (By.ID, "Acessar"),
        (By.ID, "sbmAcessar"),
        (By.XPATH, "//*[@id='Acessar']"),
        (By.XPATH, "//*[@id='sbmAcessar']"),
        (By.XPATH, "//button[contains(.,'ACESSAR') or contains(.,'Acessar')]"),
        (By.XPATH, "//input[@type='submit' and (contains(@value,'Acessar') or contains(@value,'ACESSAR'))]"),
    )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    time.sleep(2)

def pesquisar_primeiro_sei(driver: Driver, sei: str):
    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.ID, "txtPesquisaRapida")))

    inp = wait.until(EC.element_to_be_clickable((By.ID, "txtPesquisaRapida")))
    inp.click()
    inp.clear()
    inp.send_keys(sei)

    lupa = wait.until(EC.element_to_be_clickable(
        (By.XPATH, "//*[@id='spnInfraUnidade']/img")
    ))

    try:
        lupa.click()
    except Exception:
        driver.execute_script("arguments[0].click();", lupa)

    print("✅ Clique na lupa executado.")
    time.sleep(2)

def main():
    client = conectar_google_sheets()
    sh = client.open_by_key(PLANILHA_ID)
    ws = sh.get_worksheet_by_id(GID_BMS_2026)
    if ws is None:
        raise RuntimeError(f"Não achei worksheet com gid={GID_BMS_2026}")

    print(f"✅ Lendo aba gid={GID_BMS_2026} e filtrando STATUS='{STATUS_ALVO}' e SETOR ATUAL='{SETOR_ALVO}' ...")
    itens = ler_seis_enviado_gac(ws)

    print(f"\n✅ Total encontrado: {len(itens)}\n")
    if not itens:
        input("➡️ Nenhum SEI encontrado. ENTER para sair.")
        return

    print("📌 Lista de SEIs:")
    for item in itens:
        print(f"Linha {item['linha']}: {item['sei']}")

    driver = Driver(uc=True)
    driver.maximize_window()  # ✅ agora sim

    acessar_sei_login(driver, SEI_USUARIO, SEI_SENHA, SEI_UNIDADE)

    input("✅ Se houver 2FA, conclua e pressione ENTER para pesquisar o 1º SEI...")

    primeiro_sei = itens[0]["sei"]
    print(f"🔎 Pesquisando o 1º SEI: {primeiro_sei}")
    pesquisar_primeiro_sei(driver, primeiro_sei)

    input("✅ Pesquisou o 1º SEI. ENTER para encerrar...")


if __name__ == "__main__":
    main()
