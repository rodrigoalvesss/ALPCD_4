import typer
import requests
import json
import csv
import re
import sys

app = typer.Typer()

API_LIST_URL = "https://api.itjobs.pt/job/list.json"
API_GET_URL = "https://api.itjobs.pt/job/get.json"

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


@app.command()
def search(localidade: str, empresa: str, n: int):
    params = {
        "api_key": API_KEY,
        "limit": 100,
        "q": f"{empresa} {localidade}"
    }

    resp = requests.get(API_LIST_URL, headers=headers, params=params)
    if resp.status_code == 200:
        resultados = resp.json().get("results", [])

        loc_lower = localidade.lower()
        emp_lower = empresa.lower()

        filtrados = []
        for job in resultados:
            locais = job.get("locations", [])
            nome_emp = job.get("company", {}).get("name", "")
            tipo = ((job.get("jobType") or {}).get("name", "")) or job.get("type", "")

            tem_localidade = any(
                loc_lower in loc.get("name", "").lower()
                for loc in locais
            )
            tem_empresa = emp_lower in nome_emp.lower()
            eh_part_time = "part" in tipo.lower() and "time" in tipo.lower()

            if tem_localidade and tem_empresa and eh_part_time:
                filtrados.append(job)

        filtrados = filtrados[:n]

        print(json.dumps(filtrados, indent=2, ensure_ascii=False))

        if typer.confirm("Deseja exportar para CSV?") and filtrados:
            nome = f"{empresa}_{localidade}_parttime.csv".replace(" ", "_")
            exportar_csv(filtrados, nome)
    else:
        print("Erro no pedido:", resp.status_code)
