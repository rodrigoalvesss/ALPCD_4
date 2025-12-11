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
            nome = f"{empresa}_{localidade}_parttime.csv".replace(" ", "_")
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

#a) Procurar a empresa na página de ranking do Teamlyzer e devolver o URL da empresa.

def encontrar_url_empresa_teamlyzer(nome_empresa: str):

    try:
        resp = requests.get(TEAMLYZER_RANKING_URL, headers=TEAMLYZER_HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Não foi possível aceder ao ranking do Teamlyzer: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # normalizar: tirar pontuação e pôr em minúsculas
    alvo = re.sub(r"[^\w\s]", " ", nome_empresa).strip().lower()
    palavras_alvo = [p for p in alvo.split() if p]
    alvo_join = " ".join(palavras_alvo)

    if not palavras_alvo:
        return None

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        # interessam só links para empresas
        if not href.startswith("/companies/"):
            continue
        if href == "/companies/ranking":
            continue

        texto_link = link.get_text(strip=True)
        texto_norm = re.sub(r"[^\w\s]", " ", texto_link).lower()
        palavras_link = set(p for p in texto_norm.split() if p)
        texto_norm_join = " ".join(texto_norm.split())

        # critério mais flexível:
        #   - ou todas as palavras aparecem
        #   - ou o nome completo (normalizado) é substring do texto do link
        if all(p in palavras_link for p in palavras_alvo) or (alvo_join and alvo_join in texto_norm_join):
            if href.startswith("http"):
                return href
            return TEAMLYZER_BASE_URL + href

    return None


# Extrair informações da página da empresa no Teamlyzer (rating, descrição, benefícios, salário).

def extrair_info_empresa_teamlyzer(url_empresa: str):

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

    # RATING

    rating = None
    candidato = soup.find(string=re.compile(r"\b\d+[.,]\d+\s*/\s*5\b"))
    if candidato:
        m = re.search(r"(\d+[.,]\d+)", candidato)
        if m:
            try:
                rating = float(m.group(1).replace(",", "."))
            except ValueError:
                rating = None

    # DESCRIÇÃO 

    description = None
    meta_desc = soup.find("meta", {"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()
    else:
        for p in soup.find_all("p"):
            texto = p.get_text(" ", strip=True)
            if len(texto) > 40:
                description = texto
                break

    # BENEFÍCIOS

    benefits = None
    bloco_benef = None
    for h in soup.find_all(["h2", "h3", "h4"]):
        if "benef" in h.get_text(strip=True).lower():
            bloco_benef = h.find_next("ul")
            break

    if bloco_benef:
        itens = [li.get_text(" ", strip=True) for li in bloco_benef.find_all("li")]
        if itens:
            benefits = "; ".join(itens[:5])

    # SALÁRIO

    salary = None
    for node in soup.find_all(string=True):
        texto = node.strip()
        if not texto or len(texto) > 200:
            continue

        if re.search(r"(salári|salary|€|\$)", texto, re.IGNORECASE):
            salary = texto
            break

    return {
        "teamlyzer_rating": rating,
        "teamlyzer_description": description,
        "teamlyzer_benefits": benefits,
        "teamlyzer_salary": salary,
    }

# Tentar construir diretamente o URL da empresa no Teamlyzer a partir do slug do itjobs.pt.

def construir_url_empresa_por_slug(slug: str):

    if not slug:
        return None

    url = f"{TEAMLYZER_BASE_URL}/companies/{slug}"

    try:
        resp = requests.get(url, headers=TEAMLYZER_HEADERS, timeout=10)
        if resp.status_code == 200:
            return url
    except Exception as e:
        print(f"Erro ao testar URL da empresa por slug: {e}")

    return None


# Obter informações de um job específico e adicionar dados da empresa vindos do Teamlyzer.

@app.command()
def get(
    job_id: int,
    csv_file: Optional[str] = typer.Option(
        None,
        "--csv",
        help="Se indicado, exporta os dados do job enriquecido para um ficheiro CSV."
    )
):

    params = {
        "api_key": API_KEY,
        "id": job_id
    }

    resp = requests.get(API_GET_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido à API do itjobs.pt:", resp.status_code)
        mostrar_comandos()
        return

    job = resp.json()

    # Verificar erro da API
    if isinstance(job, dict) and "error" in job:
        print("Erro da API itjobs.pt:", job["error"].get("message", "Erro desconhecido"))
        mostrar_comandos()
        return

    # Tentar obter o nome e o slug da empresa
    company = job.get("company")
    if isinstance(company, dict):
        nome_empresa = company.get("name")
        slug_empresa = company.get("slug")
        nome_empresa_str = nome_empresa or "N/A"
    else:
        nome_empresa = str(company) if company else None
        slug_empresa = None
        nome_empresa_str = nome_empresa or "N/A"

    if not nome_empresa:
        print("Não foi possível determinar o nome da empresa para este job.")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    # Procurar URL da empresa no Teamlyzer:
    # 1) tentar diretamente pelo slug
    # 2) se falhar, procurar no ranking pelo nome
    url_empresa = None

    if slug_empresa:
        url_empresa = construir_url_empresa_por_slug(slug_empresa)

    if not url_empresa:
        url_empresa = encontrar_url_empresa_teamlyzer(nome_empresa)

    if not url_empresa:
        print(f"Empresa '{nome_empresa}' não encontrada no Teamlyzer.")
        # Mesmo assim mostramos o job original
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    # Extrair informações da empresa a partir do Teamlyzer
    info_teamlyzer = extrair_info_empresa_teamlyzer(url_empresa)

    # Adicionar os novos campos ao objeto do job
    job.update(info_teamlyzer)

    # Imprimir JSON final no terminal
    print(json.dumps(job, indent=2, ensure_ascii=False))

    # Exportar para CSV se o utilizador indicou um ficheiro
    if csv_file:
        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                fieldnames = [
                    "id",
                    "title",
                    "company",
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
                    "teamlyzer_rating": job.get("teamlyzer_rating"),
                    "teamlyzer_description": job.get("teamlyzer_description"),
                    "teamlyzer_benefits": job.get("teamlyzer_benefits"),
                    "teamlyzer_salary": job.get("teamlyzer_salary"),
                })
            print(f"CSV '{csv_file}' criado com sucesso!")
        except Exception as e:
            print(f"Erro ao criar CSV '{csv_file}': {e}")

    mostrar_comandos()


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
    print(">  python jobscli.py get <job_id>")
    print("   - Mostra os detalhes do job enriquecidos com dados do Teamlyzer.\n")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        mostrar_comandos()
    else:
        app()