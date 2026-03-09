from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from .models import Avaliacao
from .forms import AvaliacaoForm, AvaliacaoFormSet
from django.contrib.auth.decorators import login_required
import csv
from django.http import HttpResponse
from datetime import datetime


@login_required
def dashboard(request):
    status_counts = Avaliacao.objects.values('status').annotate(total=Count('id'))

    dados_grafico = {'pendente': 0, 'concluida': 0, 'somente_link': 0, 'saiu_empresa': 0}

    for item in status_counts:
        s = item['status']
        t = item['total']
        if s == 'Pendente' or s == 'P':
            dados_grafico['pendente'] = t
        elif s == 'Concluída' or s == 'C':
            dados_grafico['concluida'] = t
        elif 'link' in s.lower() or s == 'SLR':
            dados_grafico['somente_link'] = t
        elif 'saiu' in s.lower() or s == 'ESE':
            dados_grafico['saiu_empresa'] = t

    return render(request, 'avaliacao/dashboard.html', {'dados_grafico': dados_grafico})


@login_required
def nova_avaliacao(request):
    if request.method == 'POST':
        form = AvaliacaoForm(request.POST)
        if form.is_valid():
            form.save()  # O banco já intercepta e força para Pendente sozinho
            return redirect('avaliacao:lista_avaliacoes')
    else:
        form = AvaliacaoForm()
    return render(request, 'avaliacao/form_avaliacao.html', {'form': form, 'editando': False})


@login_required
def editar_avaliacao(request, pk):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)

    if request.method == 'POST':
        form = AvaliacaoForm(request.POST, instance=avaliacao)
        formset = AvaliacaoFormSet(request.POST, request.FILES, instance=avaliacao)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()  # Salva os PDFs fisicamente

            # O Pulo do Gato: Salva o pai DE NOVO para ele fazer a conta com os PDFs novos
            avaliacao.save()

            return redirect('avaliacao:lista_avaliacoes')
    else:
        form = AvaliacaoForm(instance=avaliacao)
        formset = AvaliacaoFormSet(instance=avaliacao)

    return render(request, 'avaliacao/form_avaliacao.html', {'form': form, 'formset': formset, 'editando': True})


@login_required
def lista_avaliacoes(request):
    registros = Avaliacao.objects.all().order_by('-data_criacao')

    # 1. Pega os dados digitados nos filtros e na barra de pesquisa
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')

    # 2. Aplica os filtros no banco de dados
    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        registros = registros.filter(status=filtro_status)

    # 3. Pega listas únicas para montar o Menu (Dropdown) do filtro no HTML
    empresas_unicas = Avaliacao.objects.values_list('empresa', flat=True).distinct()

    # Pega as siglas que existem no banco
    status_bd = Avaliacao.objects.values_list('status', flat=True).distinct()

    # Pega o dicionário de tradução do models.py
    dicionario_status = dict(Avaliacao.Status.choices)

    # Monta uma lista juntando a sigla e o nome
    status_unicos = [{'sigla': st, 'nome': dicionario_status.get(st, st)} for st in status_bd if st]

    # 4. Total de Registros visíveis na tela no momento
    total_registros = registros.count()

    contexto = {
        'registros': registros,
        'empresas_unicas': empresas_unicas,
        'status_unicos': status_unicos,
        'total_registros': total_registros
    }
    return render(request, 'avaliacao/lista_avaliacoes.html', contexto)


@login_required
def exportar_csv(request):
    # 1. Configura a resposta para ser um arquivo que o navegador vai baixar
    response = HttpResponse(content_type='text/csv')
    nome_arquivo = f'relatorio_avaliacoes_{datetime.now().strftime("%d-%m-%Y")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'

    # TRUQUE DE MESTRE: Isso força o Excel brasileiro a ler os acentos (ç, ã) corretamente
    response.write(u'\ufeff'.encode('utf8'))

    # Criamos o "escritor" da planilha (usamos ponto e vírgula para o Excel separar as colunas no Brasil)
    writer = csv.writer(response, delimiter=';')

    # 2. Escreve o Cabeçalho da Planilha
    writer.writerow(['Nome do Estagiário', 'Empresa', 'Instituição', 'Data Início', 'Data Fim', 'Status'])

    # 3. Pega os mesmos filtros que o usuário digitou na tela
    registros = Avaliacao.objects.all().order_by('-data_criacao')
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')

    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        registros = registros.filter(status=filtro_status)

    # 4. Escreve linha por linha os dados encontrados
    for reg in registros:
        writer.writerow([
            reg.nome_estagiario,
            reg.empresa,
            reg.instituicao_ensino,
            reg.data_inicio.strftime("%d/%m/%Y"),
            reg.data_fim.strftime("%d/%m/%Y"),
            reg.get_status_display()
        ])

    return response
