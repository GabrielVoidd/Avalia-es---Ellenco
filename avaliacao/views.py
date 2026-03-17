from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Min, Q, F
from .models import Avaliacao, AvaliacaoSemestral
from .forms import AvaliacaoForm, AvaliacaoFormSet
from django.contrib.auth.decorators import login_required
import csv
from django.http import HttpResponse, FileResponse
from datetime import datetime
from django.core.paginator import Paginator
import io
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet


@login_required
def dashboard(request):
    status_counts = Avaliacao.objects.values('status').annotate(total=Count('id'))

    # Adicionei a chave 'ativos' no dicionário
    dados_grafico = {'pendente': 0, 'concluida': 0, 'somente_link': 0, 'saiu_empresa': 0, 'ativos': 0}

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

    # Calcula o total de ativos somando as 3 categorias
    dados_grafico['ativos'] = dados_grafico['pendente'] + dados_grafico['concluida'] + dados_grafico['somente_link']

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
    registros = Avaliacao.objects.annotate(
        proxima_data=Min(
            'avaliacao_semestrais__data_prevista',
            filter=Q(avaliacao_semestrais__arquivo_pdf__exact='') | Q(avaliacao_semestrais__arquivo_pdf__isnull=True)
        )
    ).order_by(F('proxima_data').asc(nulls_last=True))

    # 1. Pega os dados digitados nos filtros e na barra de pesquisa
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')

    # 2. Aplica os filtros no banco de dados
    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)

    # --- A MÁGICA DO FILTRO FANTASMA AQUI ---
    if filtro_status:
        if filtro_status == 'ativos':
            # Se for "ativos", exclui quem saiu da empresa (ESE)
            registros = registros.exclude(status='ESE')
        else:
            # Se for os outros (P, C, SLR, ESE), filtra normalmente
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

    # Fatiar os registros de 20 em 20 (ou o número que você preferir)
    paginator = Paginator(registros, 20)
    numero_pagina = request.GET.get('page')
    page_obj = paginator.get_page(numero_pagina)

    # Atualiza o contexto para enviar o objeto paginado em vez da lista inteira
    contexto = {
        'registros': page_obj,
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

    # --- A MÁGICA DO FILTRO FANTASMA NO CSV TAMBÉM ---
    if filtro_status:
        if filtro_status == 'ativos':
            registros = registros.exclude(status='ESE')
        else:
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


@login_required
def deletar_avaliacao(request, pk):
    avaliacao = get_object_or_404(Avaliacao, pk=pk)

    if request.method == 'POST':
        avaliacao.delete()
        return redirect('avaliacao:lista_avaliacoes')

    return render(request, 'avaliacao/confirmar_exclusao.html', {'avaliacao': avaliacao})


@login_required
def remover_pdf_avaliacao(request, pk):
    # Pega exatamente a avaliação filha (semestral) que tem o PDF errado
    avaliacao_filha = get_object_or_404(AvaliacaoSemestral, pk=pk)

    # Guarda o ID do pai pra gente saber pra qual tela voltar depois
    id_mae = avaliacao_filha.avaliacao_mae.id

    # Se o arquivo existir, apaga do disco e limpa o banco
    if avaliacao_filha.arquivo_pdf:
        avaliacao_filha.arquivo_pdf.delete(save=True)

        # O PULO DO GATO: Salva o pai de novo!
        # Isso faz o seu models.py rodar aquela regra de negócio dos 20 dias e voltar pra Pendente
        avaliacao_filha.avaliacao_mae.save()

    # Volta pra mesma tela de edição de onde o usuário clicou
    return redirect('avaliacao:editar_avaliacao', pk=id_mae)


@login_required
def exportar_pdf(request):
    # 1. Pega os mesmos filtros da tela
    registros = Avaliacao.objects.all().order_by('-data_criacao')
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')

    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        if filtro_status == 'ativos':
            registros = registros.exclude(status='ESE')
        else:
            registros = registros.filter(status=filtro_status)

    # 2. Configura o "Papel" do PDF (A4 Deitado)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30,
                            bottomMargin=30)
    elementos = []

    # 3. Título do Documento
    estilos = getSampleStyleSheet()
    titulo = Paragraph(f"Relatório de Avaliações - {datetime.now().strftime('%d/%m/%Y')}", estilos['Heading1'])
    elementos.append(titulo)
    elementos.append(Spacer(1, 12))  # Espaço em branco

    # 4. Monta a Estrutura da Tabela
    dados_tabela = [['Estagiário', 'Empresa', 'Instituição', 'Início', 'Fim', 'Status']]

    for reg in registros:
        dados_tabela.append([
            reg.nome_estagiario[:25] + ('...' if len(reg.nome_estagiario) > 25 else ''),  # Corta nomes gigantes
            reg.empresa[:20] + ('...' if len(reg.empresa) > 20 else ''),
            reg.instituicao_ensino[:20] + ('...' if len(reg.instituicao_ensino) > 20 else ''),
            reg.data_inicio.strftime("%d/%m/%Y"),
            reg.data_fim.strftime("%d/%m/%Y"),
            reg.get_status_display()
        ])

    # 5. O Design da Tabela (Cores, Bordas, Alinhamento)
    tabela = Table(dados_tabela)
    estilo_tabela = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0d6efd")),  # Cabeçalho Azul
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),  # Letra branca no cabeçalho
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Centraliza tudo
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Cabeçalho em Negrito
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),  # Bordas da tabela
    ])

    # Faz o zebrado nas linhas pra ficar mais legível (uma branca, uma cinza clara)
    for i in range(1, len(dados_tabela)):
        if i % 2 == 0:
            estilo_tabela.add('BACKGROUND', (0, i), (-1, i), colors.HexColor("#f8f9fa"))

    tabela.setStyle(estilo_tabela)
    elementos.append(tabela)

    # 6. Gera o arquivo e manda pro navegador baixar
    doc.build(elementos)
    buffer.seek(0)

    nome_arquivo = f'relatorio_avaliacoes_{datetime.now().strftime("%d-%m-%Y")}.pdf'
    return FileResponse(buffer, as_attachment=True, filename=nome_arquivo)
