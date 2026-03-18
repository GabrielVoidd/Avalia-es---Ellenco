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
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


@login_required
def dashboard(request):
    status_counts = Avaliacao.objects.values('status').annotate(total=Count('id'))

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

    dados_grafico['ativos'] = dados_grafico['pendente'] + dados_grafico['concluida'] + dados_grafico['somente_link']

    return render(request, 'avaliacao/dashboard.html', {'dados_grafico': dados_grafico})


@login_required
def nova_avaliacao(request):
    if request.method == 'POST':
        form = AvaliacaoForm(request.POST)
        if form.is_valid():
            form.save()
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
            formset.save()
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

    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')
    filtro_mes = request.GET.get('mes')
    filtro_ano = request.GET.get('ano')

    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        if filtro_status == 'ativos':
            registros = registros.exclude(status='ESE')
        else:
            registros = registros.filter(status=filtro_status)

    if filtro_mes:
        registros = registros.filter(data_inicio__month=filtro_mes)
    if filtro_ano:
        registros = registros.filter(data_inicio__year=filtro_ano)

    empresas_unicas = Avaliacao.objects.values_list('empresa', flat=True).distinct()
    status_bd = Avaliacao.objects.values_list('status', flat=True).distinct()
    dicionario_status = dict(Avaliacao.Status.choices)
    status_unicos = [{'sigla': st, 'nome': dicionario_status.get(st, st)} for st in status_bd if st]

    total_registros = registros.count()

    paginator = Paginator(registros, 20)
    numero_pagina = request.GET.get('page')
    page_obj = paginator.get_page(numero_pagina)

    contexto = {
        'registros': page_obj,
        'empresas_unicas': empresas_unicas,
        'status_unicos': status_unicos,
        'total_registros': total_registros
    }
    return render(request, 'avaliacao/lista_avaliacoes.html', contexto)


@login_required
def exportar_csv(request):
    response = HttpResponse(content_type='text/csv')
    nome_arquivo = f'relatorio_avaliacoes_{datetime.now().strftime("%d-%m-%Y")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    response.write(u'\ufeff'.encode('utf8'))

    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Nome do Estagiário', 'Empresa', 'Instituição', 'Data Início', 'Data Fim', 'Status'])

    registros = Avaliacao.objects.all().order_by('-data_criacao')
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')
    filtro_mes = request.GET.get('mes')
    filtro_ano = request.GET.get('ano')

    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        if filtro_status == 'ativos':
            registros = registros.exclude(status='ESE')
        else:
            registros = registros.filter(status=filtro_status)

    if filtro_mes:
        registros = registros.filter(data_inicio__month=filtro_mes)
    if filtro_ano:
        registros = registros.filter(data_inicio__year=filtro_ano)

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
    avaliacao_filha = get_object_or_404(AvaliacaoSemestral, pk=pk)
    id_mae = avaliacao_filha.avaliacao_mae.id

    if avaliacao_filha.arquivo_pdf:
        avaliacao_filha.arquivo_pdf.delete(save=True)
        avaliacao_filha.avaliacao_mae.save()

    return redirect('avaliacao:editar_avaliacao', pk=id_mae)


@login_required
def exportar_pdf(request):
    registros = Avaliacao.objects.all().order_by('-data_criacao')
    query_busca = request.GET.get('q')
    filtro_empresa = request.GET.get('empresa')
    filtro_status = request.GET.get('status')
    filtro_mes = request.GET.get('mes')
    filtro_ano = request.GET.get('ano')

    if query_busca:
        registros = registros.filter(nome_estagiario__icontains=query_busca)
    if filtro_empresa:
        registros = registros.filter(empresa=filtro_empresa)
    if filtro_status:
        if filtro_status == 'ativos':
            registros = registros.exclude(status='ESE')
        else:
            registros = registros.filter(status=filtro_status)

    if filtro_mes:
        registros = registros.filter(data_inicio__month=filtro_mes)
    if filtro_ano:
        registros = registros.filter(data_inicio__year=filtro_ano)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = []

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('Titulo', parent=estilos['Heading1'], alignment=1, spaceAfter=20,
                                   textColor=colors.HexColor("#333333"))

    estilo_nome = ParagraphStyle('Nome', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor("#222222"))
    estilo_normal = ParagraphStyle('NormalCustom', fontName='Helvetica', fontSize=8,
                                   textColor=colors.HexColor("#444444"), leading=10)

    elementos.append(
        Paragraph(f"Relatório de Avaliações de Estagiários - {datetime.now().strftime('%d/%m/%Y')}", estilo_titulo))

    for reg in registros:
        nome_str = f"{reg.nome_estagiario.upper()}"
        empresa_str = f"<b>Empresa:</b> {reg.empresa.upper()}"
        status_str = f"<b>Status:</b> {reg.get_status_display().upper()}"

        periodo_str = f"<b>Período:</b> {reg.data_inicio.strftime('%d/%m/%Y')} a {reg.data_fim.strftime('%d/%m/%Y')}"
        inst_str = f"<b>Instituição:</b> {reg.instituicao_ensino}"

        p_nome = Paragraph(nome_str, estilo_nome)
        p_empresa = Paragraph(empresa_str, estilo_normal)
        p_status = Paragraph(status_str, estilo_normal)
        p_periodo = Paragraph(periodo_str, estilo_normal)
        p_inst = Paragraph(inst_str, estilo_normal)

        dados_bloco = [
            [p_nome, p_empresa, p_status],
            [p_periodo, p_inst, '']
        ]

        tabela_bloco = Table(dados_bloco, colWidths=[180, 220, 135])
        tabela_bloco.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.lightgrey),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 1), (-1, 1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 15),
        ]))
        elementos.append(tabela_bloco)

    doc.build(elementos)
    buffer.seek(0)
    nome_arquivo = f'relatorio_avaliacoes_{datetime.now().strftime("%d-%m-%Y")}.pdf'
    return FileResponse(buffer, as_attachment=True, filename=nome_arquivo)