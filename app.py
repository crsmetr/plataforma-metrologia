import streamlit.components.v1 as components
import time
import datetime
import hashlib
import os
import random
import uuid
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

PLANILHA_NOME = "Plataforma_Metrologia_DB"
LOGO_DIR = "assets_instituicao"
SIMULADORES_IMPLEMENTADOS = {"tracador", "tracador_ajuste"}


def gerar_id_unico(prefixo=""):
    return f"{prefixo}{uuid.uuid4().hex[:8]}"


@st.cache_resource
def conectar_sheets():
    if os.path.exists("credenciais.json"):
        client = gspread.service_account(filename="credenciais.json")
    else:
        client = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return client.open(PLANILHA_NOME)


def init_db():
    os.makedirs(LOGO_DIR, exist_ok=True)
    sh = conectar_sheets()

    ws_conf = sh.worksheet("configuracoes")
    if len(ws_conf.get_all_values()) <= 1:
        ws_conf.append_rows([
            ["nome_instituicao", "Plataforma de Treino em Metrologia"],
            ["logo_path", ""],
        ])

    ws_user = sh.worksheet("usuarios")
    if len(ws_user.get_all_values()) <= 1:
        senha_admin = hashlib.sha256("123".encode()).hexdigest()
        ws_user.append_row([1, "Administrador", "admin", senha_admin, "admin"])

    ws_inst = sh.worksheet("instrumentos")
    if len(ws_inst.get_all_values()) <= 1:
        ws_inst.append_rows([
            [1, "Traçador de Altura (0,02 mm)", "Traçador de Altura", 0.02, "tracador", "Leia os milímetros inteiros abaixo do zero do nônio e some os centésimos na coincidência.", 1],
            [2, "Traçador de Altura (0,05 mm)", "Traçador de Altura", 0.05, "tracador", "Cada divisão do nônio equivale a 0,05 mm. Observe o alinhamento na lupa.", 1],
            [3, "Paquímetro Universal (Em breve)", "Paquímetros", 0.02, "em_breve", "Módulo preparado para receber o código do Paquímetro.", 1],
            [4, "Micrômetro Externo (Em breve)", "Micrômetros", 0.01, "em_breve", "Módulo preparado para receber o código do Micrômetro.", 1],
            [5, "Relógio Comparador (Em breve)", "Relógios Comparadores", 0.01, "em_breve", "Módulo preparado para receber o código do Relógio Comparador.", 1],
        ])


@st.cache_data(ttl=60)
def ler_configs_cache():
    sh = conectar_sheets()
    return {str(r.get("chave")): str(r.get("valor", "")) for r in sh.worksheet("configuracoes").get_all_records()}


@st.cache_data(ttl=60)
def ler_instrumentos_cache():
    sh = conectar_sheets()
    return [{str(k).strip().lower(): v for k, v in r.items()} for r in sh.worksheet("instrumentos").get_all_records()]


def get_config(chave, padrao=""):
    return ler_configs_cache().get(chave, padrao)


def set_config(chave, valor):
    sh = conectar_sheets()
    ws = sh.worksheet("configuracoes")
    celula = ws.find(chave, in_column=1)
    if celula:
        ws.update_cell(celula.row, 2, str(valor))
    else:
        ws.append_row([chave, str(valor)])


def exibir_logo(largura=160):
    logo_path = get_config("logo_path")
    if logo_path and os.path.exists(logo_path):
        st.image(logo_path, width=largura)
        return True
    if os.path.exists("logo_instituicao.png"):
        st.image("logo_instituicao.png", width=largura)
        return True
    if os.path.exists("logo_instituicao.jpg"):
        st.image("logo_instituicao.jpg", width=largura)
        return True
    return False


def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


def autenticar(usuario, senha):
    sh = conectar_sheets()
    registros = sh.worksheet("usuarios").get_all_records()
    h = hash_senha(senha)
    for r in registros:
        if str(r.get("usuario")).strip() == usuario.strip() and str(r.get("senha_hash")) == h:
            return (r.get("id"), r.get("nome"), r.get("perfil"))
    return None


def cadastrar_aluno(nome, usuario, senha):
    sh = conectar_sheets()
    ws = sh.worksheet("usuarios")
    registros = ws.get_all_records()
    for r in registros:
        if str(r.get("usuario")).strip().lower() == usuario.strip().lower():
            return False, "Este nome de usuário já está em uso."
    novo_id = gerar_id_unico("usr_")
    ws.append_row([novo_id, nome.strip(), usuario.strip(), hash_senha(senha), "aluno"])
    return True, "Cadastro realizado com sucesso! Faça login."


def possui_simulador_ativo(inst):
    """Verifica se o instrumento esta ativo e possui codigo de simulador implementado."""
    ativo = int(inst.get("ativo", 0)) == 1
    tipo = str(inst.get("tipo_simulador", "")).strip().lower()
    nome_low = str(inst.get("nome", "")).strip().lower()
    return ativo and (tipo in SIMULADORES_IMPLEMENTADOS) and ("em breve" not in nome_low)


def normalizar_instrumento_modulo(nome_hist, insts_validos):
    """Mapeia registros antigos/variacoes do historico apenas para instrumentos com simulador ativo."""
    nome_limpo = str(nome_hist).strip()
    mapa_exato = {}
    for inst in insts_validos:
        cat = str(inst.get("categoria", "")).strip()
        nom = str(inst.get("nome", "")).strip()
        label_modulo = f"{cat} — {nom}"
        mapa_exato[nom.lower()] = label_modulo
        mapa_exato[label_modulo.lower()] = label_modulo

    if nome_limpo.lower() in mapa_exato:
        return mapa_exato[nome_limpo.lower()]

    low = nome_limpo.lower()
    eh_002 = "0,02" in low or "0.02" in low
    eh_005 = "0,05" in low or "0.05" in low
    eh_ajuste = "ajuste" in low

    for inst in insts_validos:
        cat = str(inst.get("categoria", "")).strip()
        nom = str(inst.get("nome", "")).strip()
        tipo = str(inst.get("tipo_simulador", "")).strip().lower()
        res_str = str(inst.get("resolucao", "")).replace(".", ",")
        nom_low = nom.lower()

        if "traçador" in low or "tracador" in low or "resolução" in low or "resolucao" in low:
            if "traçador" in cat.lower() or "tracador" in cat.lower():
                inst_002 = ("0,02" in nom_low or "0.02" in nom_low or "0,02" in res_str)
                inst_005 = ("0,05" in nom_low or "0.05" in nom_low or "0,05" in res_str)
                inst_ajuste = (tipo == "tracador_ajuste" or "ajuste" in nom_low)

                if eh_ajuste == inst_ajuste:
                    if (eh_002 and inst_002) or (eh_005 and inst_005):
                        return f"{cat} — {nom}"

    return None


def gerar_svg_tracador(medida, resolucao, zoom_lupa, pos_lupa, revelar=False):
    largura_svg, altura_svg = 880, 480
    base_y, col_x, esc = 445, 220, 5.4

    eh_002 = abs(float(resolucao) - 0.02) < 0.005
    num_div = 50 if eh_002 else 20
    passo_nonio = 0.98 if eh_002 else 1.95
    alt_nonio_mm = 49.0 if eh_002 else 39.0
    passo_cent = 2 if eh_002 else 5

    centesimos = round((medida - int(medida)) * 100)
    idx_coinc = int(round(centesimos / passo_cent))
    mm_coinc = round(medida + idx_coinc * passo_nonio)

    svg = [
        f'<svg viewBox="0 0 {largura_svg} {altura_svg}" style="width:100%; max-height:425px; background:#f8f9fa; border:1px solid #cbd5e1; border-radius:10px;">'
    ]

    # Desempeno e Coluna Principal
    svg.append(f'<rect x="20" y="{base_y}" width="440" height="20" fill="#444"/>')
    svg.append(f'<text x="115" y="{base_y + 14}" fill="white" font-family="Arial" font-size="11" font-weight="bold">DESEMPENO (0,00 mm)</text>')
    svg.append(f'<rect x="{col_x}" y="15" width="75" height="{base_y - 15}" fill="#dcdcdc" stroke="black"/>')

    for mm in range(0, 78):
        y = base_y - mm * esc
        destaque = False
        cor = "#00c853" if destaque else "black"
        w = 3 if destaque else (2 if mm % 10 == 0 else 1)

        if mm % 10 == 0:
            svg.append(f'<line x1="{col_x + 45}" y1="{y}" x2="{col_x + 75}" y2="{y}" stroke="{cor}" stroke-width="{w}"/>')
            svg.append(f'<text x="{col_x + 38}" y="{y + 4}" text-anchor="end" font-family="Arial" font-size="11" font-weight="bold" fill="{cor}">{mm}</text>')
        elif mm % 5 == 0:
            svg.append(f'<line x1="{col_x + 53}" y1="{y}" x2="{col_x + 75}" y2="{y}" stroke="{cor}" stroke-width="{w}"/>')
        else:
            svg.append(f'<line x1="{col_x + 60}" y1="{y}" x2="{col_x + 75}" y2="{y}" stroke="{cor}" stroke-width="{w}"/>')

    # Ponta Riscadora e Nonio
    z_y = base_y - medida * esc
    svg.append(f'<polygon points="{col_x - 85},{z_y} {col_x},{z_y - 10} {col_x},{z_y + 10}" fill="#78909c" stroke="black"/>')
    svg.append(f'<line x1="20" y1="{z_y}" x2="{col_x - 85}" y2="{z_y}" stroke="red" stroke-dasharray="4,3"/>')

    non_x = col_x + 75
    svg.append(f'<rect x="{non_x}" y="{z_y - alt_nonio_mm * esc - 8}" width="90" height="{alt_nonio_mm * esc + 16}" fill="#e3f2fd" stroke="black"/>')

    for i in range(num_div + 1):
        yt = z_y - i * passo_nonio * esc
        destaque = False
        is_major = (i % 5 == 0) if eh_002 else (i % 2 == 0)
        cor = "#00c853" if destaque else ("red" if i == 0 else "#0d47a1")
        w = 3 if destaque else (1.5 if is_major else 1)

        if is_major:
            svg.append(f'<line x1="{non_x}" y1="{yt}" x2="{non_x + 24}" y2="{yt}" stroke="{cor}" stroke-width="{w}"/>')
            lbl = ((i * 2) // 10 if i < 50 else 0) if eh_002 else ((i // 2) if i < 20 else 0)
            svg.append(f'<text x="{non_x + 30}" y="{yt + 4}" font-family="Arial" font-size="10" font-weight="bold" fill="{cor}">{lbl}</text>')
        else:
            svg.append(f'<line x1="{non_x}" y1="{yt}" x2="{non_x + 14}" y2="{yt}" stroke="{cor}" stroke-width="{w}"/>')

    # Lupa Lateral Ampliada
    lx1, ly1, lx2, ly2 = 490, 15, 860, 465
    l_esc = zoom_lupa * 3.1
    l_cy = (ly1 + ly2) / 2
    l_cmm = medida + pos_lupa
    jan_mm = ((ly2 - ly1) / l_esc) / 2

    svg.append(f'<rect x="{col_x - 5}" y="{base_y - (l_cmm + jan_mm) * esc}" width="175" height="{(jan_mm * 2) * esc}" fill="none" stroke="red" stroke-width="1.5" stroke-dasharray="4,2"/>')
    svg.append(f'<rect x="{lx1}" y="{ly1}" width="{lx2 - lx1}" height="{ly2 - ly1}" fill="white" stroke="#0059b3" stroke-width="2.5" rx="6"/>')
    div_x = 670
    l_zy = l_cy + pos_lupa * l_esc

    if revelar:
        y_match = l_cy - (mm_coinc - l_cmm) * l_esc
        if ly1 + 28 < y_match < ly2 - 10:
            svg.append(f'<rect x="{lx1 + 4}" y="{y_match - 9}" width="{lx2 - lx1 - 8}" height="18" fill="#e8f5e9"/>')

    for mm in range(max(0, int(l_cmm - jan_mm) - 1), int(l_cmm + jan_mm) + 2):
        yl = l_cy - (mm - l_cmm) * l_esc
        if ly1 + 28 < yl < ly2 - 10:
            destaque = revelar and (mm == mm_coinc)
            cor = "#00a844" if destaque else "black"
            w = 4 if destaque else (2.5 if mm % 5 == 0 else 1.5)
            svg.append(f'<line x1="{div_x - 45}" y1="{yl}" x2="{div_x}" y2="{yl}" stroke="{cor}" stroke-width="{w}"/>')
            if mm % 5 == 0 or destaque:
                txt_mm = f"{mm} mm" if destaque else str(mm)
                svg.append(f'<text x="{div_x - 52}" y="{yl + 4}" text-anchor="end" font-family="Arial" font-size="12" font-weight="bold" fill="{cor}">{txt_mm}</text>')

    for i in range(num_div + 1):
        yl = l_zy - i * passo_nonio * l_esc
        if ly1 + 28 < yl < ly2 - 10:
            destaque = revelar and (i == idx_coinc)
            is_major = (i % 5 == 0) if eh_002 else (i % 2 == 0)
            cor = "#00a844" if destaque else ("red" if i == 0 else "#0d47a1")
            w = 4 if destaque else (2.5 if is_major else 1.5)
            svg.append(f'<line x1="{div_x}" y1="{yl}" x2="{div_x + 45}" y2="{yl}" stroke="{cor}" stroke-width="{w}"/>')

            if is_major:
                lbl = ((i * 2) // 10 if i < 50 else 0) if eh_002 else ((i // 2) if i < 20 else 0)
                svg.append(f'<text x="{div_x + 54}" y="{yl + 5}" font-family="Arial" font-size="13" font-weight="bold" fill="{cor}">{lbl}</text>')

    svg.append(f'<text x="{div_x}" y="{ly1 + 20}" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold" fill="#0059b3">LUPA ({resolucao:.2f} mm | {zoom_lupa:.1f}x)</text>')
    svg.append("</svg>")
    return "".join(svg), idx_coinc


st.set_page_config(page_title="Plataforma de Metrologia", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; } html, body, [class*="css"] {
        font-size: 19px !important;
    }
    h1 {
        font-size: 2.7rem !important;
        font-weight: 800 !important;
        color: #102a43 !important;
        text-align: center !important;
        margin-bottom: 0.2rem !important;
    }
    h2 {
        font-size: 1.9rem !important;
        color: #102a43 !important;
    }
    h3 {
        font-size: 1.45rem !important;
    }
    label, .stTextInput label, .stSelectbox label, .stNumberInput label, .stTextArea label {
        font-size: 1.18rem !important;
        font-weight: 600 !important;
        color: #243b53 !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.22rem !important;
        font-weight: 700 !important;
        padding: 12px 24px !important;
    }
    input, textarea {
        font-size: 1.15rem !important;
        padding: 12px !important;
    }
    .stButton > button, .stFormSubmitButton > button {
        font-size: 1.18rem !important;
        font-weight: 700 !important;
        padding: 0.7rem 1.4rem !important;
        border-radius: 8px !important;
    }
    .stFormSubmitButton > button {
        background-color: #1565c0 !important;
        color: white !important;
        border: none !important;
    }
    .stFormSubmitButton > button:hover {
        background-color: #0d47a1 !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        font-size: 1.15rem !important;
        padding: 8px 0px !important;
    }
    [data-testid="stForm"] {
        background-color: #ffffff !important;
        padding: 32px !important;
        border-radius: 12px !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06) !important;
    }
</style>
""", unsafe_allow_html=True)

if "db_iniciado" not in st.session_state:
    init_db()
    st.session_state.db_iniciado = True

if "usuario" not in st.session_state:
    st.session_state.usuario = None

nome_instituicao = get_config("nome_instituicao", "Plataforma de Treino em Metrologia")

if st.session_state.usuario is None:
    _, col_central, _ = st.columns([0.5, 3.5, 0.5])
    with col_central:
        c_l1, c_l2, c_l3 = st.columns([0.4, 3.2, 0.4])
        with c_l2:
            if not exibir_logo(largura=560):
                st.markdown('<div style="width:100%; border:2px dashed #90a4ae; border-radius:12px; padding:28px; text-align:center; color:#607d8b; font-size:18px;"><b>LOGO DA INSTITUIÇÃO</b><br>(PNG / JPEG — Largura Ampliada)</div>', unsafe_allow_html=True)
        st.markdown(f"<h1 style='text-align:center; font-size:2.7rem; color:#102a43; margin-top:14px;'>📏 {nome_instituicao}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; font-size:1.35rem; color:#486581; margin-bottom:24px;'>Pratique leitura de instrumentos de medição diretamente no navegador.</p>", unsafe_allow_html=True)
        aba_login, aba_cadastro = st.tabs(["🔑 Entrar (Aluno / Admin)", "📝 Cadastro de Novo Aluno"])

    with aba_login:
        with st.form("form_login"):
            user_input = st.text_input("Usuário")
            pass_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                dados = autenticar(user_input, pass_input)
                if dados:
                    st.session_state.usuario = {"id": dados[0], "nome": dados[1], "perfil": dados[2]}
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

    with aba_cadastro:
        with st.form("form_cadastro"):
            novo_nome = st.text_input("Nome Completo")
            novo_user = st.text_input("Escolha um Usuário (sem espaços)")
            nova_senha = st.text_input("Crie uma Senha", type="password")
            if st.form_submit_button("Criar Conta de Aluno"):
                if novo_nome and novo_user and nova_senha:
                    ok, msg = cadastrar_aluno(novo_nome, novo_user, nova_senha)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                else:
                    st.warning("Preencha todos os campos.")

else:
    user = st.session_state.usuario

    with st.sidebar:
        if not exibir_logo(largura=180):
            st.markdown('<div style="border:2px dashed #b0bec5; border-radius:8px; padding:14px; text-align:center; color:#78909c; font-size:12px; margin-bottom:10px;">Espaço reservado para o<br><b>Logo da Instituição</b></div>', unsafe_allow_html=True)
        st.caption(nome_instituicao)
        st.divider()
        st.title(f"👤 {user['nome']}")
        st.caption(f"Perfil: **{user['perfil'].upper()}**")

        if st.button("Sair", use_container_width=True):
            st.session_state.usuario = None
            st.rerun()

        st.divider()
        st.subheader("📂 Instrumentos Disponíveis")

    sh = conectar_sheets()
    todos_inst = ler_instrumentos_cache()
    lista_inst = [i for i in todos_inst if int(i.get("ativo", 0)) == 1]

    opcoes_menu = [f"{inst['categoria']} — {inst['nome']}" for inst in lista_inst]
    if user["perfil"] == "admin":
        opcoes_menu.append("⚙️ PAINEL DO ADMINISTRADOR")

    escolha = st.sidebar.radio("Selecione o módulo:", opcoes_menu)

    if escolha == "⚙️ PAINEL DO ADMINISTRADOR":
        st.header("⚙️ Painel de Gerenciamento do Administrador")

        with st.expander("📊 Filtrar por Aluno — Desempenho por Instrumento", expanded=True):
            ws_u_hist = sh.worksheet("usuarios")
            regs_usuarios = ws_u_hist.get_all_records()
            alunos_lista = [r for r in regs_usuarios if str(r.get("perfil", "")).strip().lower() == "aluno"]

            if not alunos_lista:
                st.info("Nenhum aluno cadastrado ainda.")
            else:
                col_f1, col_f2 = st.columns([3.2, 0.8])
                with col_f1:
                    opcoes_alunos = {f"{r.get('nome')} ({r.get('usuario')})": r.get("id") for r in alunos_lista}
                    aluno_sel_label = st.selectbox("Selecione o Aluno:", list(opcoes_alunos.keys()), key="filtro_aluno_admin")
                with col_f2:
                    st.markdown("<div style='height: 31px;'></div>", unsafe_allow_html=True)
                    if st.button("🔄 Atualizar", use_container_width=True, key="btn_atualizar_filtro_aluno"):
                        st.cache_data.clear()
                        st.rerun()

                aluno_sel_id = str(opcoes_alunos[aluno_sel_label]).strip()

                # Considera apenas instrumentos registrados, ativos e com codigo de simulador implementado
                insts_com_simulador = [i for i in todos_inst if possui_simulador_ativo(i)]

                ws_hist = sh.worksheet("historico")
                valores_hist = ws_hist.get_all_values()

                if len(valores_hist) > 0 and str(valores_hist[0][1]).strip().lower() in ["usuario_id", "id_usuario", "aluno_id", "user_id"]:
                    linhas_hist = valores_hist[1:]
                else:
                    linhas_hist = valores_hist

                ordem_modulo = [f"{inst['categoria']} — {inst['nome']}" for inst in insts_com_simulador]
                resumo_inst = {}

                for row in linhas_hist:
                    if len(row) >= 4 and str(row[1]).strip() == aluno_sel_id:
                        nome_modulo = normalizar_instrumento_modulo(row[2], insts_com_simulador)
                        if not nome_modulo:
                            continue

                        try:
                            acertou_h = int(float(str(row[3]).strip()))
                        except ValueError:
                            acertou_h = 0

                        if nome_modulo not in resumo_inst:
                            resumo_inst[nome_modulo] = {"total": 0, "acertos": 0, "erros": 0}
                        resumo_inst[nome_modulo]["total"] += 1
                        if acertou_h == 1:
                            resumo_inst[nome_modulo]["acertos"] += 1
                        else:
                            resumo_inst[nome_modulo]["erros"] += 1

                if not resumo_inst:
                    st.warning("Este aluno ainda não realizou nenhuma medição nos instrumentos com simulador ativo.")
                else:
                    tabela_resultado = []
                    for nome_mod in ordem_modulo:
                        if nome_mod in resumo_inst and resumo_inst[nome_mod]["total"] > 0:
                            dados_h = resumo_inst[nome_mod]
                            qtd = dados_h["total"]
                            ac = dados_h["acertos"]
                            er = dados_h["erros"]
                            pct = (ac / qtd * 100) if qtd > 0 else 0.0
                            tabela_resultado.append({
                                "Instrumento": nome_mod,
                                "Quantidade de medições": qtd,
                                "Acertos": ac,
                                "Erros": er,
                                "Resultado do desempenho": f"{pct:.1f}%"
                            })
                    st.dataframe(tabela_resultado, use_container_width=True, hide_index=True)

        with st.expander("🔐 Segurança: Alterar Login e Senha do Administrador", expanded=True):
            with st.form("form_troca_cred_admin"):
                novo_login_adm = st.text_input("Novo Usuário de Acesso (Login)", value=user.get("usuario", "admin"))
                s_atual = st.text_input("Senha Atual (obrigatório para confirmar)", type="password")
                s_nova = st.text_input("Nova Senha", type="password")
                s_conf = st.text_input("Confirme a Nova Senha", type="password")
                if st.form_submit_button("💾 Salvar Novo Login e Senha"):
                    if not novo_login_adm.strip() or not s_atual or not s_nova:
                        st.warning("Preencha todos os campos.")
                    elif s_nova != s_conf:
                        st.error("A nova senha e a confirmação não coincidem.")
                    else:
                        ws_u = sh.worksheet("usuarios")
                        regs = ws_u.get_all_records()
                        atualizado = False
                        for idx_u, r in enumerate(regs, start=2):
                            if str(r.get("perfil")).strip() == "admin" and str(r.get("senha_hash")) == hash_senha(s_atual):
                                ws_u.update_cell(idx_u, 3, novo_login_adm.strip())
                                ws_u.update_cell(idx_u, 4, hash_senha(s_nova))
                                atualizado = True
                                break
                        if atualizado:
                            st.success("Login e senha atualizados no Google Sheets!")
                        else:
                            st.error("Senha atual incorreta.")

        with st.expander("🏫 Identidade Visual e Logotipo da Instituição", expanded=True):
            col_id1, col_id2 = st.columns([2, 1])
            with col_id1:
                novo_nome_inst = st.text_input("Nome da Escola / Instituição / Empresa", value=nome_instituicao)
                arquivo_logo = st.file_uploader("Enviar Logotipo (PNG, JPG ou JPEG)", type=["png", "jpg", "jpeg"])
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("💾 Salvar Identidade Visual", use_container_width=True):
                    set_config("nome_instituicao", novo_nome_inst.strip())
                    if arquivo_logo is not None:
                        ext = os.path.splitext(arquivo_logo.name)[1].lower()
                        caminho_destino = os.path.join(LOGO_DIR, f"logo_atual{ext}")
                        with open(caminho_destino, "wb") as f:
                            f.write(arquivo_logo.getbuffer())
                        set_config("logo_path", caminho_destino)
                    st.success("Identidade visual atualizada com sucesso!")
                    st.cache_data.clear()
                    st.rerun()
                if c_btn2.button("🗑️ Remover Logotipo", use_container_width=True):
                    logo_antigo = get_config("logo_path")
                    if logo_antigo and os.path.exists(logo_antigo):
                        os.remove(logo_antigo)
                    set_config("logo_path", "")
                    st.info("Logotipo removido.")
                    st.cache_data.clear()
                    st.rerun()
            with col_id2:
                st.write("**Pré-visualização atual:**")
                if not exibir_logo(largura=220):
                    st.info("Nenhum logotipo enviado ainda.")

        with st.expander("➕ Cadastrar Novo Instrumento no Menu", expanded=True):
            with st.form("novo_inst_form"):
                col1, col2 = st.columns(2)
                nome_inst = col1.text_input("Nome do Instrumento (ex: Paquímetro 0,05 mm)")
                cat_inst = col2.selectbox("Categoria no Menu", ["Traçador de Altura", "Paquímetros", "Micrômetros", "Relógios Comparadores", "Goniômetros", "Outros"])
                res_inst = col1.number_input("Resolução (ex: 0.02, 0.05, 0.01)", value=0.02, step=0.01, format="%.2f")
                tipo_sim = col2.selectbox("Motor Gráfico", ["tracador", "tracador_ajuste", "em_breve"])
                instr_texto = st.text_area("Instruções para o Aluno")
                if st.form_submit_button("Salvar Instrumento na Plataforma"):
                    if nome_inst:
                        ws_i = sh.worksheet("instrumentos")
                        novo_id = gerar_id_unico("inst_")
                        ws_i.append_row([novo_id, nome_inst, cat_inst, res_inst, tipo_sim, instr_texto, 1])
                        st.success(f"Instrumento '{nome_inst}' adicionado ao Google Sheets!")
                        st.cache_data.clear()
                        st.rerun()

        st.subheader("📋 Instrumentos Cadastrados no Google Sheets")
        ws_i = sh.worksheet("instrumentos")
        for idx_row, item in enumerate(todos_inst, start=2):
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{item.get('nome')}** ({item.get('categoria')})")
            c2.write(f"Resolução: {item.get('resolucao')} mm | Motor: `{item.get('tipo_simulador')}`")
            ativo_atual = int(item.get("ativo", 1))
            status = "Ativo" if ativo_atual == 1 else "Oculto"
            if c3.button(f"{status}", key=f"tog_{item.get('id', idx_row)}"):
                ws_i.update_cell(idx_row, 7, 0 if ativo_atual == 1 else 1)
                st.cache_data.clear()
                st.rerun()

    else:
        idx_sel = opcoes_menu.index(escolha)
        inst_atual = lista_inst[idx_sel]
        inst_id = inst_atual.get("id", idx_sel + 1)
        inst_nome = inst_atual.get("nome", "Instrumento")
        inst_nome_completo = f"{inst_atual.get('categoria', '')} — {inst_nome}"
        inst_res = 0.02 if ("0,02" in str(inst_atual) or "0.02" in str(inst_atual)) else 0.05
        inst_tipo = str(inst_atual.get("tipo_simulador", "tracador")).strip()
        inst_instr = inst_atual.get("instrucoes", "")

        st.header(f"📐 {inst_nome}")
        if inst_instr:
            st.info(inst_instr)

        if inst_tipo == "tracador":
            chave_medida = f"medida_{inst_id}"
            chave_rev = f"revelar_{inst_id}"
            chave_bloq = f"bloq_ajuda_{inst_id}"
            chave_fim_tempo = f"fim_tempo_{inst_id}"
            chave_placar = f"placar_{inst_id}"
            chave_feedback = f"feedback_{inst_id}"

            def sortear_nova():
                if abs(inst_res - 0.02) < 0.005:
                    return round(random.randint(250, 1250) * 0.02, 2)
                return round(random.randint(100, 500) * 0.05, 2)

            if chave_medida not in st.session_state:
                st.session_state[chave_medida] = sortear_nova()
                st.session_state[chave_rev] = False
                st.session_state[chave_bloq] = random.random() < 0.45
                st.session_state[chave_fim_tempo] = None
                st.session_state[chave_placar] = {"acertos": 0, "erros": 0}
                st.session_state[chave_feedback] = None

            # --- BARRA SUPERIOR COMPACTA (TEMPO E CONTROLES DA LUPA) ---
            ct1, ct2, ct3, ct4, ct5 = st.columns([1.2, 0.9, 1.0, 1.1, 1.3])
            opcao_tempo = ct1.selectbox(
                "⏱️ Tempo:",
                ["Livre (Sem tempo)", "15 min", "30 min", "45 min", "60 min"],
                key=f"sel_t_{inst_id}"
            )
            if ct2.button("▶️ Iniciar", use_container_width=True, key=f"btn_ini_{inst_id}"):
                st.session_state[chave_placar] = {"acertos": 0, "erros": 0}
                st.session_state[chave_feedback] = None
                st.session_state[chave_medida] = sortear_nova()
                st.session_state[chave_rev] = False
                st.session_state[chave_bloq] = random.random() < 0.45
                if opcao_tempo != "Livre (Sem tempo)":
                    minutos = int(opcao_tempo.split()[0])
                    st.session_state[chave_fim_tempo] = time.time() + (minutos * 60)
                else:
                    st.session_state[chave_fim_tempo] = None
                st.rerun()

            tempo_esgotado = False
            if st.session_state[chave_fim_tempo] is not None:
                restante = int(st.session_state[chave_fim_tempo] - time.time())
                if restante <= 0:
                    tempo_esgotado = True
                    ct3.error("⏰ **ESGOTADO!**")
                else:
                    mins, segs = divmod(restante, 60)
                    ct3.info(f"⏳ **{mins:02d}:{segs:02d}**")
            else:
                ct3.info("⏳ **Modo Livre**")

            zoom_val = ct4.slider("🔍 Zoom Lupa", 5.0, 10.0, 7.5, 0.5)
            limite_lupa = 50.0 if abs(inst_res - 0.02) < 0.005 else 40.0
            pos_lupa = ct5.slider("↕️ Deslizar Lupa", -2.0, limite_lupa, 2.0, 1.0)

            pl = st.session_state[chave_placar]

            if tempo_esgotado:
                total_tent = pl["acertos"] + pl["erros"]
                aprov = (pl["acertos"] / total_tent * 100) if total_tent > 0 else 0
                st.warning(f"🏁 **Sessão encerrada!** Você realizou **{total_tent}** leituras com **{aprov:.0f}%** de aproveitamento ({pl['acertos']} acertos e {pl['erros']} erros). Clique em **▶️ Iniciar** para treinar novamente.")
            else:
                # --- LAYOUT LADO A LADO: INSTRUMENTO A ESQUERDA | PLACAR E RESPOSTA AO LADO DO NONIO ---
                col_desenho, col_lateral = st.columns([2.7, 1.1])

                with col_desenho:
                    svg_html, _ = gerar_svg_tracador(
                        st.session_state[chave_medida],
                        inst_res,
                        zoom_val,
                        pos_lupa,
                        revelar=st.session_state[chave_rev],
                    )
                    st.markdown(svg_html, unsafe_allow_html=True)
                    components.html("""
                    <script>
                    setTimeout(() => {
                        const doc = window.parent.document;
                        const svgs = doc.querySelectorAll("svg");
                        const svg = svgs[svgs.length - 1];
                        if (svg) {
                            svg.style.cursor = "ns-resize";
                            svg.onwheel = function(e) {
                                e.preventDefault();
                                e.stopPropagation();
                                const sliders = doc.querySelectorAll('div[role="slider"]');
                                const alvo = sliders.length > 1 ? sliders[1] : sliders[0];
                                if (alvo) {
                                    alvo.focus();
                                    const subindo = e.deltaY < 0;
                                    alvo.dispatchEvent(new KeyboardEvent("keydown", {
                                        key: subindo ? "ArrowRight" : "ArrowLeft",
                                        code: subindo ? "ArrowRight" : "ArrowLeft",
                                        keyCode: subindo ? 39 : 37,
                                        which: subindo ? 39 : 37,
                                        bubbles: true,
                                        cancelable: true
                                    }));
                                }
                            };
                        }
                    }, 250);
                    </script>
                    """, height=0)

                with col_lateral:
                    # Placar em destaque bem ao lado do Nonio / Lupa
                    st.markdown(f"""
                    <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:10px; padding:14px; margin-bottom:10px; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                        <div style="font-size:15px; font-weight:700; color:#334e68; margin-bottom:8px; text-align:center;">📊 DESEMPENHO NA SESSÃO</div>
                        <div style="display:flex; justify-content:space-around; text-align:center;">
                            <div style="background:#e8f5e9; border-radius:8px; padding:8px 14px; width:46%;">
                                <div style="font-size:24px; font-weight:800; color:#1b5e20;">{pl['acertos']}</div>
                                <div style="font-size:13px; font-weight:700; color:#2e7d32;">ACERTOS</div>
                            </div>
                            <div style="background:#ffebee; border-radius:8px; padding:8px 14px; width:46%;">
                                <div style="font-size:24px; font-weight:800; color:#b71c1c;">{pl['erros']}</div>
                                <div style="font-size:13px; font-weight:700; color:#c62828;">ERROS</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Campo de resposta com Enter rapido
                    with st.form(key=f"form_resp_{inst_id}", clear_on_submit=True):
                        resposta_str = st.text_input("Leitura (mm) + ENTER:", placeholder="Ex: 14.36")
                        enviado = st.form_submit_button("✅ Confirmar", use_container_width=True)

                        if enviado:
                            try:
                                val_user = float(resposta_str.replace(",", ".").strip())
                                medida_certa = st.session_state[chave_medida]
                                acertou = 1 if abs(val_user - medida_certa) < 0.001 else 0

                                ws_h = sh.worksheet("historico")
                                data_agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                                ws_h.append_row([gerar_id_unico("reg_"), user["id"], inst_nome_completo, acertou, data_agora])

                                if acertou:
                                    st.session_state[chave_placar]["acertos"] += 1
                                    st.session_state[chave_feedback] = ("ok", f"🎉 **CORRETO!** Anterior: **{medida_certa:.2f} mm**")
                                else:
                                    st.session_state[chave_placar]["erros"] += 1
                                    st.session_state[chave_feedback] = ("err", f"❌ **ERROU!** Digitado: {val_user:.2f} | Certo: **{medida_certa:.2f} mm**")

                                st.session_state[chave_medida] = sortear_nova()
                                st.session_state[chave_rev] = False
                                st.session_state[chave_bloq] = random.random() < 0.45
                                st.rerun()
                            except ValueError:
                                st.warning("Digite um número válido.")

                    ajuda_bloqueada = st.session_state.get(chave_bloq, False)
                    if ajuda_bloqueada:
                        st.button("🔒 Ajuda Bloqueada (Desafio)", disabled=True, use_container_width=True, key=f"btn_ver_{inst_id}")
                        st.caption("⚠️ Nesta leitura, encontre o traço coincidente sem auxílio visual.")
                    else:
                        if st.button("👁️ Ver Coincidência", use_container_width=True, key=f"btn_ver_{inst_id}"):
                            st.session_state[chave_rev] = True
                            st.rerun()

                    # Resultado da leitura anterior exibido logo abaixo dos botoes
                    if st.session_state[chave_feedback]:
                        tipo_fb, msg_fb = st.session_state[chave_feedback]
                        if tipo_fb == "ok":
                            st.success(msg_fb)
                        else:
                            st.error(msg_fb)
        elif inst_tipo == "tracador_ajuste":
            ch_alvo, ch_atual, ch_rev = f"alvo_{inst_id}", f"pos_atual_{inst_id}", f"rev_aj_{inst_id}"
            ch_fim, ch_pl, ch_fb = f"fim_aj_{inst_id}", f"pl_aj_{inst_id}", f"fb_aj_{inst_id}"
            passo_res = 0.02 if abs(inst_res - 0.02) < 0.005 else 0.05

            def sortear_alvo():
                return round(random.randint(250, 1250) * 0.02, 2) if passo_res == 0.02 else round(random.randint(100, 500) * 0.05, 2)

            if ch_alvo not in st.session_state:
                st.session_state[ch_alvo] = sortear_alvo()
                st.session_state[ch_atual] = 5.00
                st.session_state[f"sl_aj_{inst_id}"] = 5.00
                st.session_state[ch_rev] = False
                st.session_state[ch_fim] = None
                st.session_state[ch_pl] = {"acertos": 0, "erros": 0}
                st.session_state[ch_fb] = None

            ct1, ct2, ct3, ct4 = st.columns([1.2, 0.9, 1.0, 1.4])
            op_tempo = ct1.selectbox("⏱️ Tempo:", ["Livre (Sem tempo)", "15 min", "30 min", "45 min", "60 min"], key=f"st_aj_{inst_id}")
            if ct2.button("▶️ Iniciar", use_container_width=True, key=f"bi_aj_{inst_id}"):
                st.session_state[ch_pl] = {"acertos": 0, "erros": 0}
                st.session_state[ch_fb] = None
                st.session_state[ch_alvo] = sortear_alvo()
                st.session_state[ch_atual] = 5.00
                st.session_state[f"sl_aj_{inst_id}"] = 5.00
                st.session_state[ch_rev] = False
                st.session_state[ch_fim] = time.time() + (int(op_tempo.split()[0]) * 60) if op_tempo != "Livre (Sem tempo)" else None
                st.rerun()

            esgotado = False
            if st.session_state[ch_fim] is not None:
                rest = int(st.session_state[ch_fim] - time.time())
                if rest <= 0:
                    esgotado = True
                    ct3.error("⏰ **ESGOTADO!**")
                else:
                    m, s = divmod(rest, 60)
                    ct3.info(f"⏳ **{m:02d}:{s:02d}**")
            else:
                ct3.info("⏳ **Modo Livre**")

            c_z1, c_z2 = ct4.columns(2)
            zoom_aj = c_z1.slider("🔍 Zoom", 5.0, 10.0, 7.5, 0.5, key=f"zm_aj_{inst_id}")
            lim_aj = 50.0 if passo_res == 0.02 else 40.0
            pos_lupa_aj = c_z2.slider("↕️ Lupa", -2.0, lim_aj, 15.0, 1.0, key=f"plp_aj_{inst_id}")
            pl = st.session_state[ch_pl]

            if esgotado:
                tot = pl["acertos"] + pl["erros"]
                ap = (pl["acertos"] / tot * 100) if tot > 0 else 0
                st.warning(f"🏁 **Sessão encerrada!** {tot} tentativas | **{ap:.0f}%** de aproveitamento.")
            else:
                st.markdown("<style>[data-testid='stSliderThumbValue'] { display: none !important; }</style>", unsafe_allow_html=True)
                medida_corrente = st.slider("🖱️ Arraste na régua com o mouse (ou mova a barra / scroll):", 0.00, 26.00, float(st.session_state[ch_atual]), passo_res, key=f"sl_aj_{inst_id}")
                st.session_state[ch_atual] = round(medida_corrente, 2)

                col_des, col_lat = st.columns([2.7, 1.1])
                with col_des:
                    svg_aj, _ = gerar_svg_tracador(st.session_state[ch_atual], inst_res, zoom_aj, pos_lupa=pos_lupa_aj, revelar=st.session_state[ch_rev])
                    st.markdown(svg_aj, unsafe_allow_html=True)
                    components.html("""
                    <script>
                    setTimeout(() => {
                        const doc = window.parent.document;
                        const svgs = doc.querySelectorAll("svg");
                        const svg = svgs[svgs.length - 1];
                        if (svg) {
                            svg.style.cursor = "grab";
                            let arrastando = false, startY = 0;
                            const moverPassos = (passos) => {
                                const sliders = doc.querySelectorAll('div[role="slider"]');
                                const alvo = sliders[sliders.length - 1];
                                if (!alvo || passos === 0) return;
                                alvo.focus();
                                const tecla = passos > 0 ? "ArrowRight" : "ArrowLeft";
                                const code = passos > 0 ? 39 : 37;
                                for (let k = 0; k < Math.abs(passos); k++) {
                                    alvo.dispatchEvent(new KeyboardEvent("keydown", {key: tecla, code: tecla, keyCode: code, which: code, bubbles: true}));
                                }
                            };
                            svg.onmousedown = (e) => {
                                const rect = svg.getBoundingClientRect();
                                if ((e.clientX - rect.left) / rect.width < 0.55) { arrastando = true; startY = e.clientY; svg.style.cursor = "grabbing"; e.preventDefault(); }
                            };
                            doc.onmousemove = (e) => {
                                if (!arrastando) return;
                                const dy = startY - e.clientY;
                                if (Math.abs(dy) >= 4) { moverPassos(Math.trunc(dy / 4)); startY = e.clientY; }
                            };
                            doc.onmouseup = () => { if (arrastando) { arrastando = false; svg.style.cursor = "grab"; } };
                            svg.onwheel = (e) => {
                                e.preventDefault();
                                const rect = svg.getBoundingClientRect();
                                const relX = (e.clientX - rect.left) / rect.width;
                                const sliders = doc.querySelectorAll('div[role="slider"]');
                                // Se o mouse estiver sobre a lupa (direita), desliza a lupa; se estiver na regua (esquerda), move o tracador
                                const alvo = relX >= 0.55 ? sliders[sliders.length - 2] : sliders[sliders.length - 1];
                                if (alvo) {
                                    alvo.focus();
                                    const tecla = e.deltaY < 0 ? "ArrowRight" : "ArrowLeft";
                                    const code = e.deltaY < 0 ? 39 : 37;
                                    alvo.dispatchEvent(new KeyboardEvent("keydown", {key: tecla, code: tecla, keyCode: code, which: code, bubbles: true}));
                                }
                            };
                        }
                    }, 250);
                    </script>
                    """, height=0)

                with col_lat:
                    st.markdown(f'<div style="background:#e3f2fd; border:2px solid #1565c0; border-radius:10px; padding:12px; margin-bottom:10px; text-align:center;"><div style="font-size:13px; font-weight:700; color:#0d47a1;">🎯 AJUSTE O TRAÇADOR PARA:</div><div style="font-size:28px; font-weight:900; color:#1565c0;">{st.session_state[ch_alvo]:.2f} mm</div></div><div style="background:#fff; border:1px solid #cbd5e1; border-radius:10px; padding:10px; margin-bottom:10px;"><div style="display:flex; justify-content:space-around; text-align:center;"><div style="background:#e8f5e9; border-radius:8px; padding:6px 12px; width:46%;"><div style="font-size:22px; font-weight:800; color:#1b5e20;">{pl["acertos"]}</div><div style="font-size:12px; font-weight:700; color:#2e7d32;">ACERTOS</div></div><div style="background:#ffebee; border-radius:8px; padding:6px 12px; width:46%;"><div style="font-size:22px; font-weight:800; color:#b71c1c;">{pl["erros"]}</div><div style="font-size:12px; font-weight:700; color:#c62828;">ERROS</div></div></div></div>', unsafe_allow_html=True)
                    def mover_fino(delta):
                        novo_v = max(0.0, min(26.0, round(st.session_state[ch_atual] + delta, 2)))
                        st.session_state[ch_atual] = novo_v
                        st.session_state[f"sl_aj_{inst_id}"] = novo_v

                    bf1, bf2 = st.columns(2)
                    bf1.button(f"⬇️ -{passo_res:.2f}", use_container_width=True, key=f"m_menos_{inst_id}", on_click=mover_fino, args=(-passo_res,))
                    bf2.button(f"⬆️ +{passo_res:.2f}", use_container_width=True, key=f"m_mais_{inst_id}", on_click=mover_fino, args=(passo_res,))
                    with st.form(key=f"form_aj_{inst_id}"):
                        if st.form_submit_button("✅ Confirmar Posição (Enter)", use_container_width=True):
                            alvo_val, pos_val = st.session_state[ch_alvo], st.session_state[ch_atual]
                            acertou = 1 if abs(pos_val - alvo_val) < 0.001 else 0
                            ws_h = sh.worksheet("historico")
                            ws_h.append_row([gerar_id_unico("reg_"), user["id"], inst_nome_completo, acertou, datetime.datetime.now().strftime("%d/%m/%Y %H:%M")])
                            if acertou:
                                st.session_state[ch_pl]["acertos"] += 1
                                st.session_state[ch_fb] = ("ok", f"🎉 **EXATO!** Você ajustou em **{alvo_val:.2f} mm**!")
                            else:
                                st.session_state[ch_pl]["erros"] += 1
                                st.session_state[ch_fb] = ("err", f"❌ **ERROU!** Ficou em **{pos_val:.2f} mm** (pedido: **{alvo_val:.2f} mm**).")
                            st.session_state[ch_alvo] = sortear_alvo()
                            st.session_state[ch_rev] = False
                            st.rerun()
                    if st.session_state[ch_fb]:
                        tfb, mfb = st.session_state[ch_fb]
                        if tfb == "ok":
                            st.success(mfb)
                        else:
                            st.error(mfb)

        else:
            st.warning("🚧 Este módulo já está registrado no menu da plataforma e pronto para receber o código do simulador.")
