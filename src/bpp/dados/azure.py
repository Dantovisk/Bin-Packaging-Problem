import pandas as pd

N_AMOSTRAS = 30

# Definimos os nomes das 11 colunas na ordem exata do CSV
colunas_azure = [
    "vmid", "subscriptionid", "deploymentid", "vmcreated", "vmdeleted", 
    "max_cpu", "avg_cpu", "p95_cpu", "vmcategory", 
    "vmcorecount", "vmmemory"
]

# Lê as primeiras N linhas 
# O Pandas aceita ler direto do arquivo .gz compactado
df_bruto = pd.read_csv("trace_data_vmtable_vmtable.csv.gz", names=colunas_azure, nrows=N_AMOSTRAS)

# Filtra apenas as 3 colunas que importam para o modelo de Bin Packing
df_bpp = df_bruto[["vmid", "vmcorecount", "vmmemory"]]

# Salva o arquivo limpo para os solvers (Gurobi/SCIP)
df_bpp.to_csv(f"data/instancias/instancia_{N_AMOSTRAS}_vms.csv", index=False)

print("Amostra gerada com sucesso:")
print(df_bpp.head())