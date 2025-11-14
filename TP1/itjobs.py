import typer
import requests
import json
import csv
import re
import sys
from datetime import datetime
from operator import itemgetter


app = typer.Typer()

API_LIST_URL = "https://api.itjobs.pt/job/list.json"
API_GET_URL = "https://api.itjobs.pt/job/get.json"
API_SEARCH_URL = "https://api.itjobs.pt/job/search.json"

API_KEY = "d160d8c93e8e49486873b9f6f60d3822"

headers = {
    "User-Agent": "Mozilla/5.0 (ALPCD CLI)"
}

def exportar_csv(ofertas, ficheiro):
    """Exporta as ofertas para CSV com os campos pedidos no enunciado."""
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

@app.command()
def top(n: int):
    """
    a) Listar os N trabalhos mais recentes publicados no itjobs.pt.
    """
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


@app.command()
def search(localidade: str, empresa: str, n: int):
    """
    b) Listar trabalhos do tipo PART-TIME publicados por uma empresa numa localidade.
    Output em JSON. Opcionalmente exporta CSV.
    """
    params = {
        "api_key": API_KEY,
        "q": empresa,
        "type": 2,
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

    print(json.dumps(filtrados, indent=2, ensure_ascii=False))

    if filtrados and typer.confirm("Deseja exportar para CSV?"):
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

@app.command()
def type(job_id: str):
    """
    c) Extrair o regime de trabalho de um determinado job id.
    """
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

@app.command()
def skills(data_inicial: str, data_final: str):
    """
    d) Contar ocorrências de skills nas descrições entre duas datas (YYYY-MM-DD).
    """
    try:
        di, df = map(datetime.fromisoformat, (data_inicial, data_final))
    except ValueError:
        print("Datas inválidas. Usa o formato YYYY-MM-DD.")
        mostrar_comandos()
        return

    params = {"api_key": API_KEY, "limit": 200}
    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code != 200:
        print("Erro no pedido:", resp.status_code)
        mostrar_comandos()
        return

    resultados = resp.json().get("results", [])

    skills = ["python", "java", "javascript", "sql", "docker"]
    contagens = dict.fromkeys(skills, 0)

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
        for s in skills:
            contagens[s] += len(re.findall(rf"\b{s}\b", texto))

    ordenado = sorted(contagens.items(), key=itemgetter(1), reverse=True)
    resultado_json = [{skill: count} for skill, count in ordenado if count > 0]


    print(json.dumps(resultado_json, indent=2, ensure_ascii=False))
    mostrar_comandos()



def mostrar_comandos():
    print("------------------------------------------------------------")
    print("Pode utilizar o programa com os seguintes comandos:\n")
    print(">  python TP1/itjobs.py top n")
    print("   - Mostra os n empregos mais recentes.\n")
    print('>  python TP1/itjobs.py search <Localidade> "<Empresa>" <n>')
    print("   - Lista n trabalhos dessa empresa nessa localidade.\n")
    print(">  python TP1/itjobs.py type <job_id>")
    print("   - Mostra o regime de trabalho (remoto/híbrido/presencial/outro).\n")
    print(">  python TP1/itjobs.py skills <data_inicial (YYYY-MM-DD)> <data_final (YYYY-MM-DD)>")
    print("   - Conta ocorrências de skills nas descrições nesse intervalo.\n")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        mostrar_comandos()
    else:
        app()