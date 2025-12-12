import typer
import requests
import json
import csv
import re
import sys
from datetime import datetime
from operator import itemgetter
from bs4 import BeautifulSoup
from typing import Optional
from urllib.parse import quote
import unicodedata
from collections import Counter



app = typer.Typer()

API_LIST_URL = "https://api.itjobs.pt/job/list.json"
API_GET_URL = "https://api.itjobs.pt/job/get.json"
API_SEARCH_URL = "https://api.itjobs.pt/job/search.json"

API_KEY = "d160d8c93e8e49486873b9f6f60d3822"

headers = {
    "User-Agent": "Mozilla/5.0 (ALPCD CLI)"
}

TEAMLYZER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TeamlyzerScraper/1.0)"
}

TEAMLYZER_RANKING_URL = "https://pt.teamlyzer.com/companies/ranking"
TEAMLYZER_BASE_URL = "https://pt.teamlyzer.com"

def exportar_csv(ofertas, ficheiro): #Exporta as ofertas para CSV com os campos pedidos no enunciado.

    with open(ficheiro, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["titulo", "empresa", "descricao", "data_publicacao", "salario", "localizacao"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for job in ofertas:
            writer.writerow({
                "titulo": job.get("title", "N/A"),
                "empresa": job.get("company", {}).get("name", "N/A"),
                "descricao": job.get("body", "N/A"),
                "data_publicacao": job.get("publishedAt", "N/A"),
                "salario": job.get("wage", "N/A"),
                "localizacao": ", ".join(
                    loc.get("name", "") for loc in job.get("locations", [])
                ),
            })
    print(f"CSV '{ficheiro}' criado com sucesso!")

### TP1 ###

#a) Listar os N trabalhos mais recentes publicados no itjobs.pt.

@app.command()
def top(n: int):

    if n <= 0:
            print("O número de ofertas tem de ser maior que 0.")
            mostrar_comandos()
            return
    
    params = {
        "api_key": API_KEY,
        "limit": n
    }

    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code == 200:
        resultados = resp.json().get("results", [])
        print(json.dumps(resultados, indent=2, ensure_ascii=False))

        if typer.confirm("Deseja exportar para CSV?"):
            exportar_csv(resultados, "top_ofertas.csv")
    else:
        print("Erro no pedido:", resp.status_code)
    
    mostrar_comandos()

#b) Listar trabalhos do tipo PART-TIME publicados por uma empresa numa localidade.

@app.command()
def search(localidade: str, empresa: str, n: int):

    if n <= 0:
            print("O número de ofertas tem de ser maior que 0.")
            mostrar_comandos()
            return
    
    params = {
        "api_key": API_KEY,
        "limit": 200
    }

    resp = requests.get(API_SEARCH_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        mostrar_comandos()
        return

    resultados = resp.json().get("results", [])

    loc_lower = localidade.lower()
    emp_lower = empresa.lower()

    def is_part_time(job: dict) -> bool:
        tipos = job.get("types", [])
        return any(re.search(r"\bpart[- ]?time\b", t.get("name", ""), re.I) for t in tipos)

    filtrados = []
    for job in resultados:
        locais = job.get("locations", [])
        nome_emp = job.get("company", {}).get("name", "")

        tem_localidade = any(
            loc_lower in loc.get("name", "").lower()
            for loc in locais
        )
        tem_empresa = emp_lower in nome_emp.lower()

        if tem_localidade and tem_empresa and is_part_time(job):
            filtrados.append(job)

    filtrados = filtrados[:n]

    if not filtrados:
        print("Não foram encontrados trabalhos PART-TIME para essa empresa/localidade.")
    else:
        print(json.dumps(filtrados, indent=2, ensure_ascii=False))
        if typer.confirm("Deseja exportar para CSV?"):
            nome = f"{empresa}{localidade}_parttime.csv".replace(" ", "")
            exportar_csv(filtrados, nome)

    mostrar_comandos()


def detectar_regime(texto: str) -> str:
    t = texto.lower()
    if re.search(r"remoto|remote|teletrabalho", t):
        return "remoto"
    if re.search(r"híbrido|hibrido|hybrid", t):
        return "híbrido"
    if re.search(r"presencial|on[- ]?site|onsite", t):
        return "presencial"
    return "outro"

#c) Extrair o regime de trabalho de um determinado job id.

@app.command()
def type(job_id: str):

    params = {
        "api_key": API_KEY,
        "id": job_id
    }

    resp = requests.get(API_GET_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        mostrar_comandos()
        return

    job = resp.json()

    if isinstance(job, dict) and "error" in job:
        print("Erro da API:", job["error"].get("message", "Erro desconhecido"))
        mostrar_comandos()
        return

    texto = (job.get("title", "") + " " + job.get("body", "")).lower()

    regime = detectar_regime(texto)

    if regime == "outro":
        allow_remote = job.get("allowRemote", None)
        locations = job.get("locations", [])
        tem_localizacao = len(locations) > 0

        if allow_remote is True:
            if re.search(r"híbrido|hibrido|hybrid", texto):
                regime = "híbrido"
            else:
                regime = "remoto"
        elif allow_remote is False and tem_localizacao:
            regime = "presencial"
        else:
            regime = "outro"

    print(regime)

    mostrar_comandos()

#d) Contar ocorrências de skills nas descrições entre duas datas (YYYY-MM-DD).

@app.command()
def skills(data_inicial: str, data_final: str):

    try:
        di, df = map(datetime.fromisoformat, (data_inicial, data_final))
    except ValueError:
        print("Datas inválidas. Usa o formato YYYY-MM-DD.")
        mostrar_comandos()
        return

    if di > df:
        print("A data inicial tem de ser anterior ou igual à data final.")
        mostrar_comandos()
        return

    params = {"api_key": API_KEY, "limit": 200}
    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        mostrar_comandos()
        return

    resultados = resp.json().get("results", [])

    lista_skills = ["python", "java", "javascript", "sql", "docker"]
    contagens = dict.fromkeys(lista_skills, 0)

    for job in resultados:
        pub_str = job.get("publishedAt", "")[:10]
        if not pub_str:
            continue

        try:
            data_pub = datetime.fromisoformat(pub_str)
        except ValueError:
            continue

        if not (di <= data_pub <= df):
            continue

        texto = (job.get("title", "") + " " + job.get("body", "")).lower()
        for s in lista_skills:
            contagens[s] += len(re.findall(rf"\b{s}\b", texto))

    ordenado = sorted(contagens.items(), key=itemgetter(1), reverse=True)
    resultado_json = [{skill: count} for skill, count in ordenado if count > 0]

    if not resultado_json:
        print("Não foram encontradas ocorrências dessas skills nesse intervalo de datas.")
    else:
        print(json.dumps(resultado_json, indent=2, ensure_ascii=False))

    mostrar_comandos()

### TP2 ###

#a)     Procura a empresa na página de ranking do Teamlyzer e devolve o URL da página da empresa (ou None).

def encontrar_url_empresa_teamlyzer(nome_empresa: str, slug: Optional[str] = None) -> Optional[str]:
    """
    Tenta encontrar o URL da empresa no Teamlyzer.

    1) Primeiro tenta construir diretamente a partir do slug do itjobs.pt:
       https://pt.teamlyzer.com/companies/<slug>
    2) Se não der, faz fallback para o ranking, procurando links de /companies/...
    """

    # 1) Tentar com o slug, se existir
    if slug:
        candidate_url = f"{TEAMLYZER_BASE_URL}/companies/{slug}"
        try:
            resp = requests.get(candidate_url, headers=TEAMLYZER_HEADERS, timeout=10)
            if resp.status_code == 200:
                return candidate_url
        except Exception:
            # se falhar, continua para o ranking
            pass

    # 2) Fallback: ranking
    try:
        resp = requests.get(TEAMLYZER_RANKING_URL, headers=TEAMLYZER_HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Não foi possível aceder ao ranking do Teamlyzer: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    alvo = (nome_empresa or "").strip().lower()
    slug_norm = (slug or "").lower()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("/companies/") or href == "/companies/ranking":
            continue

        texto = link.get_text(" ", strip=True).lower()

        # critério: ou o slug aparece no href, ou o nome aparece no texto
        if slug_norm and slug_norm in href.lower():
            return TEAMLYZER_BASE_URL + href
        if alvo and alvo in texto:
            return TEAMLYZER_BASE_URL + href

    return None

def extrair_info_empresa_teamlyzer(url_empresa: str) -> dict:

#    Vai à página da empresa no Teamlyzer e tenta extrair: rating, descrição, benefícios e uma frase sobre salário.

    try:
        resp = requests.get(url_empresa, headers=TEAMLYZER_HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erro ao aceder à página da empresa no Teamlyzer: {e}")
        return {
            "teamlyzer_rating": None,
            "teamlyzer_description": None,
            "teamlyzer_benefits": None,
            "teamlyzer_salary": None,
        }

    soup = BeautifulSoup(resp.text, "html.parser")

    rating = None
    txt_rating = soup.find(string=re.compile(r"\b\d+[.,]\d+\s*/\s*5\b"))
    if txt_rating:
        m = re.search(r"(\d+[.,]\d+)", txt_rating)
        if m:
            try:
                rating = float(m.group(1).replace(",", "."))
            except ValueError:
                rating = None

    description = None
    meta = soup.find("meta", {"name": "description"})
    if meta and meta.get("content"):
        description = meta["content"].strip()
    else:
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            if len(t) > 40:
                description = t
                break

    benefits = None
    for h in soup.find_all(["h2", "h3", "h4"]):
        if "benef" in h.get_text(strip=True).lower():
            ul = h.find_next("ul")
            if ul:
                itens = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                if itens:
                    benefits = "; ".join(itens)
            break

    # SALÁRIO (primeira frase que mencione salário ou símbolo € / $)
    salary = None
    for node in soup.find_all(string=True):
        t = node.strip()
        if not t or len(t) > 200:
            continue
        if re.search(r"(salári|salary|€|\$)", t, re.IGNORECASE):
            salary = t
            break

    return {
        "teamlyzer_rating": rating,
        "teamlyzer_description": description,
        "teamlyzer_benefits": benefits,
        "teamlyzer_salary": salary,
    }

@app.command()
def get(
    job_id: int,
    csv_file: Optional[str] = typer.Option(
        None,
        "--csv",
        help="Se indicado, exporta os dados do job enriquecido para um ficheiro CSV."
    )
):
    
    params = {"api_key": API_KEY, "id": job_id}
    try:
        resp = requests.get(API_GET_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Erro ao aceder à API do itjobs.pt: {e}")
        mostrar_comandos()
        return

    job = resp.json()


    if isinstance(job, dict) and "error" in job:
        print("Erro da API itjobs.pt:", job["error"].get("message", "Erro desconhecido"))
        mostrar_comandos()
        return

    # nome da empresa + slug (se existir)
    company = job.get("company")
    slug_empresa = None

    if isinstance(company, dict):
        nome_empresa = company.get("name")
        slug_empresa = company.get("slug")
        nome_empresa_str = nome_empresa or "N/A"
    else:
        nome_empresa = str(company) if company else None
        nome_empresa_str = nome_empresa or "N/A"

    if not nome_empresa:
        print("Não foi possível determinar o nome da empresa para este job.")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    # aqui já passamos também o slug para aumentar a probabilidade de encontrar a empresa
    url_empresa = encontrar_url_empresa_teamlyzer(nome_empresa, slug_empresa)
    if not url_empresa:
        print(f"Empresa '{nome_empresa}' não encontrada no Teamlyzer. JSON original do job:")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    if not url_empresa:
        print(f"Empresa '{nome_empresa}' não encontrada no Teamlyzer. JSON original do job:")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    info_teamlyzer = extrair_info_empresa_teamlyzer(url_empresa)
    job.update(info_teamlyzer)

    print(json.dumps(job, indent=2, ensure_ascii=False))

    # CSV opcional (alínea d para o comando get)
    if csv_file:
        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                fieldnames = [
                    "id",
                    "title",
                    "company",
                    "teamlyzer_url",
                    "teamlyzer_rating",
                    "teamlyzer_description",
                    "teamlyzer_benefits",
                    "teamlyzer_salary",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "id": job.get("id", "N/A"),
                    "title": job.get("title", "N/A"),
                    "company": nome_empresa_str,
                    "teamlyzer_url": url_empresa,
                    "teamlyzer_rating": job.get("teamlyzer_rating"),
                    "teamlyzer_description": job.get("teamlyzer_description"),
                    "teamlyzer_benefits": job.get("teamlyzer_benefits"),
                    "teamlyzer_salary": job.get("teamlyzer_salary"),
                })
            print(f"CSV '{csv_file}' criado com sucesso!")
        except Exception as e:
            print(f"Erro ao criar CSV '{csv_file}': {e}")


    mostrar_comandos()


#b)     Conta vagas por zona e por tipo de trabalho. Pode ainda exportar CSV: Zona | Tipo de Trabalho | Nº de vagas.

@app.command()
def statistics(
    zone: str = typer.Argument(..., help="Zona/Região a analisar"),
    csv_file: Optional[str] = typer.Option(None, "--csv", help="Exportar para CSV")
):

    params = {"api_key": API_KEY, "limit": 200}
    try:
        resp = requests.get(API_LIST_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Erro ao aceder à API do itjobs.pt: {e}")
        mostrar_comandos()
        return

    resultados = resp.json().get("results", [])

    zona_norm = zone.lower()

    contagens = {}

    for job in resultados:
        titulo = job.get("title", "N/A")

        for loc in job.get("locations", []):
            nome_loc = loc.get("name", "").lower()

            if zona_norm in nome_loc:
                chave = (loc.get("name", "N/A"), titulo)
                contagens[chave] = contagens.get(chave, 0) + 1

    resultado = [
        {"zona": zona, "tipo_trabalho": tipo, "vagas": count}
        for (zona, tipo), count in contagens.items()
    ]

    print(json.dumps(resultado, indent=2, ensure_ascii=False))


    mostrar_comandos()

#c

# =============================
# TP2 — ALÍNEA c) (corrigida)
# =============================

def normalizar_texto(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def obter_html(url: str) -> str:
    resp = requests.get(
        url,
        headers={
            **TEAMLYZER_HEADERS,
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Referer": TEAMLYZER_BASE_URL + "/",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.text


def _extrair_options_do_select(soup: BeautifulSoup, keywords: list[str]) -> list[tuple[str, str]]:
    selects = []
    for sel in soup.find_all("select"):
        blob = " ".join([
            sel.get("id", "") or "",
            sel.get("name", "") or "",
            " ".join(sel.get("class", []) if isinstance(sel.get("class"), list) else []),
        ]).lower()

        if any(k in blob for k in keywords):
            selects.append(sel)

    opts = []
    for sel in selects:
        for opt in sel.find_all("option"):
            val = (opt.get("value") or "").strip()
            txt = opt.get_text(" ", strip=True).strip()
            if val and txt:
                opts.append((txt, val))
    return opts


def resolver_profession_role(job: str) -> Optional[str]:
    url = f"{TEAMLYZER_BASE_URL}/companies/jobs?order=most_relevant"
    html = obter_html(url)
    soup = BeautifulSoup(html, "html.parser")

    cargos = _extrair_options_do_select(
        soup,
        keywords=["profession_role"]
    )

    if not cargos:
        return None

    alvo = normalizar_texto(job)

    best_val = None
    best_score = 0

    for txt, val in cargos:
        t = normalizar_texto(txt)
        v = normalizar_texto(val)

        t_clean = re.sub(r"\s*\(\d+\)\s*", "", t).strip()

        score = 0
        if alvo == t_clean:
            score = 100
        elif alvo in t_clean:
            score = 80
        elif t_clean in alvo:
            score = 60

        # extra: match por slug/value (muito útil)
        if alvo.replace(" ", "-") in v:
            score = max(score, 90)

        if score > best_score:
            best_score = score
            best_val = val


    return best_val if best_score > 0 else None


def obter_top10_skills(job: str, top: int = 10) -> list[dict]:

    # 1) Resolver o cargo para o value do profession_role
    profession_role = resolver_profession_role(job)
    if not profession_role:
        return []

    # 2) Abrir página já filtrada pelo cargo
    url = (
        f"{TEAMLYZER_BASE_URL}/companies/jobs"
        f"?profession_role={quote(profession_role)}&order=most_relevant"
    )
    html = obter_html(url)
    soup = BeautifulSoup(html, "html.parser")

    # 3) Extrair apenas o select correto de stack/tags
    tags = _extrair_options_do_select(
        soup,
        keywords=["stack", "tag"]
    )

    contagens = {}

    for txt, val in tags:
        # Esperamos texto do tipo "python (49)"
        m = re.search(r"\((\d+)\)", txt)
        if not m:
            continue

        count = int(m.group(1))
        if count <= 0:
            continue

        # Preferir o value (slug) quando existe
        skill = normalizar_texto(val) or normalizar_texto(txt)
        skill = re.sub(r"\s*\(\d+\)\s*", "", skill).strip()

        # Filtros de segurança
        if not skill:
            continue
        if skill in {"all", "todos", "todas"}:
            continue

        # Garantir que não duplica com valores menores
        contagens[skill] = max(contagens.get(skill, 0), count)

    resultado = [
        {"skill": skill, "count": count}
        for skill, count in contagens.items()
    ]
    resultado.sort(key=lambda x: x["count"], reverse=True)

    return resultado[:top]


@app.command("list-skills")
def list_skills(
    job: str = typer.Argument(..., help='Ex: "data scientist"'),
    top: int = typer.Option(10, "--top", help="Top N skills"),
    csv_file: Optional[str] = typer.Option(None, "--csv", help="Exportar para CSV")
):
    resultado = obter_top10_skills(job, top=top)

    if not resultado:
        print("Não foi possível resolver o cargo (profession_role) ou não foram encontradas skills.")
        return

    print(json.dumps(resultado, indent=2, ensure_ascii=False))



def mostrar_comandos():
    print("------------------------------------------------------------")
    print("Pode utilizar o programa com os seguintes comandos:\n")

    print(">  python jobscli.py top n")
    print("   - Mostra os n empregos mais recentes.\n")

    print('>  python jobscli.py search <Localidade> "<Empresa>" <n>')
    print("   - Lista n trabalhos part-time dessa empresa nessa localidade.\n")

    print(">  python jobscli.py type <job_id>")
    print("   - Mostra o regime de trabalho (remoto/híbrido/presencial/outro).\n")

    print(">  python jobscli.py skills <data_inicial (YYYY-MM-DD)> <data_final (YYYY-MM-DD)>")
    print("   - Conta ocorrências de skills nas descrições nesse intervalo.\n")

    print(">  python jobscli.py statistics <Zona> [--csv ficheiro.csv]")
    print("   - Conta vagas por zona e por tipo de trabalho.")
    

    print(">  python jobscli.py get <job_id> [--csv ficheiro.csv]")
    print("   - (TP2 a) Mostra os detalhes do job enriquecidos com dados do Teamlyzer.")
    

    print('>  python jobscli.py list-skills "<job>" [--top N] [--csv ficheiro.csv]')
    print("   - (TP2 c) Mostra em JSON as top N skills para esse tipo de trabalho.")
    




if _name_ == "_main_":
    if len(sys.argv) == 1:
        mostrar_comandos()
    else:
        app()