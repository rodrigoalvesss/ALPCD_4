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

app = typer.Typer()
list_app = typer.Typer()

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

def exportar_csv(ofertas, ficheiro):

    with open(ficheiro, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["titulo", "empresa", "descricao", "data_publicacao", "salario", "localizacao"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for job in ofertas:

            empresa = job.get("company")
            if isinstance(empresa, dict):
                empresa = empresa.get("name", "N/A")
            else:
                empresa = empresa or "N/A"

            descricao = BeautifulSoup(job.get("body", "") or "", "html.parser").get_text(" ", strip=True) or "N/A"


            salario = job.get("wage") or "N/A"

            locais = [loc.get("name", "").strip() for loc in job.get("locations", []) if loc.get("name")]
            localizacao = ", ".join(locais) if locais else "N/A"

            writer.writerow({
                "titulo": job.get("title", "N/A"),
                "empresa": empresa,
                "descricao": descricao,
                "data_publicacao": job.get("publishedAt", "N/A"),
                "salario": salario,
                "localizacao": localizacao,
            })

    print(f"CSV '{ficheiro}' criado com sucesso!")


### TP1 ###

#a) Listar os N trabalhos mais recentes publicados no itjobs.pt.

@app.command()
def top(n: int, csv_file: Optional[str] = typer.Option(None, "--csv")):

    if n <= 0:
            print("O número de ofertas tem de ser maior que 0.")
            return
    
    params = {"api_key": API_KEY,"limit": n}

    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        return

    resultados = resp.json().get("results", [])
    print(json.dumps(resultados, indent=2, ensure_ascii=False))

    if csv_file:
        exportar_csv(resultados, csv_file)

#b) Listar trabalhos do tipo PART-TIME publicados por uma empresa numa localidade.

@app.command()
def search(localidade: str, empresa: str, n: int, csv_file: Optional[str] = typer.Option(None, "--csv")):
    if n <= 0:
        print("O número de ofertas tem de ser maior que 0.")
        return

    params = {"api_key": API_KEY, "limit": 200}

    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        return

    resultados = resp.json().get("results", [])

    loc_lower = localidade.lower()
    emp_lower = empresa.lower()

    def is_part_time(job):
        tipos = job.get("types", [])
        return any(re.search(r"\bpart[- ]?time\b", t.get("name", ""), re.I) for t in tipos)

    filtrados = []
    for job in resultados:
        locais = job.get("locations", [])
        nome_emp = job.get("company", {}).get("name", "")

        tem_localidade = any(loc_lower in loc.get("name", "").lower() for loc in locais)
        tem_empresa = emp_lower in nome_emp.lower()

        if tem_localidade and tem_empresa and is_part_time(job):
            filtrados.append(job)

    filtrados = filtrados[:n]

    if not filtrados:
        print("Não foram encontrados trabalhos PART-TIME para essa empresa/localidade.")
        return

    print(json.dumps(filtrados, indent=2, ensure_ascii=False))

    if csv_file:
        exportar_csv(filtrados, csv_file)

# c) Extrair o regime de trabalho de um determinado job id.

def detectar_regime(texto: str) -> str:
    t = texto.lower()
    if re.search(r"remoto|remote|teletrabalho", t):
        return "remoto"
    if re.search(r"híbrido|hibrido|hybrid", t):
        return "híbrido"
    if re.search(r"presencial|on[- ]?site|onsite", t):
        return "presencial"
    return "outro"


@app.command()
def type(job_id: int):
    params = {"api_key": API_KEY, "id": job_id}

    resp = requests.get(API_GET_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        return

    job = resp.json()

    if isinstance(job, dict) and "error" in job:
        print("Erro da API:", job["error"].get("message", "Erro desconhecido"))
        return

    texto = job.get("title", "") + " " + job.get("body", "")
    regime = detectar_regime(texto)

    if regime == "outro":
        allow_remote = job.get("allowRemote")
        locations = job.get("locations", [])

        if allow_remote is True:
            regime = "remoto"
        elif allow_remote is False and locations:
            regime = "presencial"

    print(regime)
 
# d) Contar ocorrências de skills nas descrições entre duas datas (YYYY-MM-DD).

@app.command()
def skills(data_inicial: str, data_final: str):
    try:
        di, df = map(datetime.fromisoformat, (data_inicial, data_final))
    except ValueError:
        print("Datas inválidas. Usa o formato YYYY-MM-DD.")
        return

    if di > df:
        print("A data inicial tem de ser anterior ou igual à data final.")
        return

    params = {"api_key": API_KEY, "limit": 200}
    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
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

    print(json.dumps(resultado_json, indent=2, ensure_ascii=False))


### TP2 ###

#a) Procura a empresa na página de ranking do Teamlyzer e devolve o URL da página da empresa (ou None).

def obter_html_teamlyzer(url: str) -> str:
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


def encontrar_url_empresa_teamlyzer(nome_empresa: str, slug: Optional[str] = None) -> Optional[str]:
    if slug:
        candidate_url = f"{TEAMLYZER_BASE_URL}/companies/{slug}"
        try:
            resp = requests.get(candidate_url, headers=TEAMLYZER_HEADERS, timeout=10)
            if resp.status_code == 200:
                return candidate_url
        except Exception:
            pass

    try:
        html = obter_html_teamlyzer(TEAMLYZER_RANKING_URL)
    except Exception as e:
        print(f"Não foi possível aceder ao ranking do Teamlyzer: {e}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    alvo = (nome_empresa or "").strip().lower()
    slug_norm = (slug or "").lower()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("/companies/") or href == "/companies/ranking":
            continue

        texto = link.get_text(" ", strip=True).lower()

        if slug_norm and slug_norm in href.lower():
            return TEAMLYZER_BASE_URL + href
        if alvo and alvo in texto:
            return TEAMLYZER_BASE_URL + href

    return None

def extrair_beneficios_teamlyzer(url_empresa: str) -> Optional[str]:
    url_b = url_empresa.rstrip("/") + "/benefits-and-values"
    try:
        html = obter_html_teamlyzer(url_b)
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")

    h_benef = soup.find("h2", class_="text-muted", string=re.compile(r"Benefícios e vantagens", re.I))
    if not h_benef:
        return None

    beneficios = []
    for node in h_benef.find_all_next():
        if node.name == "h2" and "valores e cultura" in node.get_text(" ", strip=True).lower():
            break

        if node.name == "h3":
            b = node.find("b")
            if b:
                t = b.get_text(" ", strip=True)
                if t:
                    beneficios.append(t)

        if node.name == "div" and "flex_details" in (node.get("class") or []):
            t = node.get_text(" ", strip=True)
            if t:
                beneficios.append(t)

    vistos = set()
    uniq = []
    for t in beneficios:
        k = t.lower()
        if k not in vistos:
            vistos.add(k)
            uniq.append(t)

    return "; ".join(uniq) if uniq else None


def extrair_salario_medio_teamlyzer(url_empresa: str) -> Optional[str]:
    url_s = url_empresa.rstrip("/") + "/salary-reviews"
    try:
        html = obter_html_teamlyzer(url_s)
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")

    for bloco in soup.find_all(string=re.compile(r"Salário médio bruto", re.I)):
        container = bloco.parent

        for _ in range(3):
            if container is None:
                break
            texto = container.get_text(" ", strip=True)

            m = re.search(r"([0-9\.\s]+€)\s*-\s*([0-9\.\s]+€)", texto)
            if m:
                a = re.sub(r"\s+", " ", m.group(1)).strip()
                b = re.sub(r"\s+", " ", m.group(2)).strip()
                return f"{a} - {b}"

            container = container.parent

    return None



def extrair_info_empresa_teamlyzer(url_empresa: str) -> dict:
    try:
        html = obter_html_teamlyzer(url_empresa)
    except Exception as e:
        print(f"Erro ao aceder à página da empresa no Teamlyzer: {e}")
        return {
            "teamlyzer_rating": None,
            "teamlyzer_description": None,
            "teamlyzer_benefits": None,
            "teamlyzer_salary": None,
        }

    soup = BeautifulSoup(html, "html.parser")

    rating = None
    meta_rating = soup.find("meta", {"itemprop": "ratingValue"})
    if meta_rating and meta_rating.get("content"):
        try:
            rating = float(meta_rating["content"].replace(",", "."))
        except ValueError:
            rating = None

    description = None

    meta_schema_desc = soup.find("meta", {"itemprop": "description"})
    if meta_schema_desc and meta_schema_desc.get("content"):
        description = meta_schema_desc["content"].strip()

    if not description:
        meta_og = soup.find("meta", {"property": "og:description"})
        if meta_og and meta_og.get("content"):
            description = meta_og["content"].strip()

    if not description:
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = meta_desc["content"].strip()

    if description:
        dlow = description.lower()
        if "reviews e opiniões" in dlow or "teamlyzer" in dlow:
            description = None

    benefits = extrair_beneficios_teamlyzer(url_empresa)
    salary = extrair_salario_medio_teamlyzer(url_empresa)

    return {
        "teamlyzer_rating": rating,
        "teamlyzer_description": description,
        "teamlyzer_benefits": benefits,
        "teamlyzer_salary": salary,
    }


@app.command()
def get(job_id: int, csv_file: Optional[str] = typer.Option(None, "--csv", help="Se indicado, exporta os dados do job enriquecido para um ficheiro CSV.")):

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

    url_empresa = encontrar_url_empresa_teamlyzer(nome_empresa, slug_empresa)
    if not url_empresa:
        print(f"Empresa '{nome_empresa}' não encontrada no Teamlyzer. JSON original do job:")
        print(json.dumps(job, indent=2, ensure_ascii=False))
        mostrar_comandos()
        return

    info_teamlyzer = extrair_info_empresa_teamlyzer(url_empresa)
    job.update(info_teamlyzer)
    job["teamlyzer_url"] = url_empresa

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


#b) Conta vagas por zona e por tipo de trabalho. Pode ainda exportar CSV: Zona | Tipo de Trabalho | Nº de vagas.

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

    if not contagens:
        print("Não foram encontradas vagas para essa zona.")
        mostrar_comandos()
        return

    resultado = [
        {"zona": z, "tipo_trabalho": tipo, "vagas": count}
        for (z, tipo), count in contagens.items()
    ]
    resultado.sort(key=lambda x: x["vagas"], reverse=True)

    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    if csv_file:
        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Zona", "Tipo de Trabalho", "Nº de vagas"])
                for row in resultado:
                    writer.writerow([row["zona"], row["tipo_trabalho"], row["vagas"]])
            print(f"CSV '{csv_file}' criado com sucesso!")
        except Exception as e:
            print("Erro ao criar CSV:", e)


    mostrar_comandos()


#c) Determinar as top n skills mais relevantes para um determinado cargo profissional"


def normalizar_texto(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower()).strip()


def resolver_cargo_teamlyzer(cargo: str) -> Optional[str]:
    url_base = f"{TEAMLYZER_BASE_URL}/companies/jobs?order=most_relevant"
    soup = BeautifulSoup(obter_html_teamlyzer(url_base), "html.parser")

    select_role = soup.find("select", id="profession_role")
    if not select_role:
        return None

    alvo = normalizar_texto(cargo)
    melhor_valor = None
    melhor_score = -1

    for opt in select_role.find_all("option"):
        valor = (opt.get("value") or "").strip()
        texto = opt.get_text(" ", strip=True)
        texto = normalizar_texto(re.sub(r"\(\d+\)", "", texto))

        if not valor or valor == "-" or not texto:
            continue

        score = 0
        if texto == alvo:
            score = 3
        elif alvo in texto:
            score = 2
        elif texto in alvo:
            score = 1

        if score > melhor_score:
            melhor_score = score
            melhor_valor = valor

    return melhor_valor if melhor_score > 0 else None


def extrair_top_skills_teamlyzer(cargo: str, top: int = 10) -> list:
    role = resolver_cargo_teamlyzer(cargo)
    if not role:
        return []

    url = f"{TEAMLYZER_BASE_URL}/companies/jobs?profession_role={quote(role)}&order=most_relevant"
    soup = BeautifulSoup(obter_html_teamlyzer(url), "html.parser")

    select_tags = soup.find("select", id="tags")
    if not select_tags:
        return []

    resultado = []

    for opt in select_tags.find_all("option"):
        skill = (opt.get("value") or "").strip()
        texto = opt.get_text(" ", strip=True)

        if not skill or skill == "-" or skill.lower() in {"all", "todos", "todas"}:
            continue

        m = re.search(r"\((\d+)\)", texto)
        if not m:
            continue

        resultado.append({
            "skill": skill,
            "count": int(m.group(1))
        })

    resultado.sort(key=lambda x: x["count"], reverse=True)
    return resultado[:top]


@list_app.command("skills")
def list_skills(
    job: str = typer.Argument(..., help="Cargo profissional (ex: 'data scientist')"),
    top: int = typer.Option(10, "--top", help="Número de skills"),
    csv_file: Optional[str] = typer.Option(None, "--csv", help="Exportar CSV"),
):
    resultado = extrair_top_skills_teamlyzer(job, top)

    if not resultado:
        print("Não foi possível encontrar o cargo ou as skills.")
        return

    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    if csv_file:
        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["job", "skill", "count"])
                for item in resultado:
                    writer.writerow([job, item["skill"], item["count"]])
            print(f"CSV '{csv_file}' criado com sucesso!")
        except Exception as e:
            print(f"Erro ao criar CSV: {e}")


app.add_typer(list_app, name="list")


##################################################################################


def mostrar_comandos():
    print("------------------------------------------------------------")
    print("Pode utilizar o programa com os seguintes comandos:\n")

    print(">  python jobscli.py top <n> [--csv ficheiro.csv]")
    print("   - Mostra os n empregos mais recentes.")
    print("   - Se indicar --csv, exporta para CSV.\n")

    print('>  python jobscli.py search <Localidade> "<Empresa>" <n> [--csv ficheiro.csv]')
    print("   - Lista n trabalhos part-time dessa empresa nessa localidade.")
    print("   - Se indicar --csv, exporta para CSV.\n")

    print(">  python jobscli.py type <job_id>")
    print("   - Mostra o regime de trabalho (remoto/híbrido/presencial/outro).\n")

    print(">  python jobscli.py skills <data_inicial YYYY-MM-DD> <data_final YYYY-MM-DD>")
    print("   - Conta ocorrências de skills nas descrições nesse intervalo (output JSON).\n")

    print(">  python jobscli.py statistics <Zona> [--csv ficheiro.csv]")
    print("   - Conta vagas por zona e por tipo de trabalho.")
    print("   - Se indicar --csv, guarda um CSV: Zona | Tipo de Trabalho | Nº de vagas.\n")

    print(">  python jobscli.py get <job_id> [--csv ficheiro.csv]")
    print("   - (TP2 a) Mostra o job enriquecido com dados do Teamlyzer.")
    print("   - (TP2 d) Se indicar --csv, guarda um CSV com os campos principais.\n")

    print('>  python jobscli.py list skills "<job>" [--top N] [--csv ficheiro.csv]')
    print("   - (TP2 c) Mostra em JSON as top N skills para esse tipo de trabalho.")
    print("   - (TP2 d) Se indicar --csv, guarda também um CSV: job | skill | count.\n")



if __name__ == "__main__":
    if len(sys.argv) == 1:
        mostrar_comandos()
    else:
        app()
