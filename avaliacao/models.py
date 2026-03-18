from django.core.exceptions import ValidationError
from django.db import models
import calendar
from datetime import date


class Avaliacao(models.Model):
    class Status(models.TextChoices):
        P = 'P', 'Pendente'
        C = 'C', 'Concluída'
        SLR = 'SLR', 'Somente o link foi respondido'
        ESE = 'ESE', 'Estagiário(a) saiu da empresa'

    nome_estagiario = models.CharField(max_length=200, verbose_name='Nome do(a) estagiário(a)')
    empresa = models.CharField(max_length=250, verbose_name='Razão social ou nome fantasia da empresa')
    instituicao_ensino = models.CharField(max_length=250, verbose_name='Nome da escola ou faculdade')
    data_inicio = models.DateField()
    data_fim = models.DateField()

    # NOVO CAMPO: Data de Rescisão
    data_rescisao = models.DateField(null=True, blank=True, verbose_name='Data de Rescisão')

    status = models.CharField(max_length=3, choices=Status.choices)
    observacoes = models.TextField(null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    # NOVIDADE: As validações de ouro contra erros de digitação
    def clean(self):
        super().clean()

        # 1. Impede viagem no tempo (Anos menores que 2024)
        if self.data_inicio and self.data_inicio.year < 2024:
            raise ValidationError({'data_inicio': 'O ano de início não pode ser anterior a 2024.'})

        if self.data_fim and self.data_fim.year < 2024:
            raise ValidationError({'data_fim': 'O ano de fim não pode ser anterior a 2024.'})

        if self.data_rescisao and self.data_rescisao.year < 2024:
            raise ValidationError({'data_rescisao': 'O ano de rescisão não pode ser anterior a 2024.'})

        # 2. Impede datas iguais
        if self.data_inicio and self.data_fim and self.data_inicio == self.data_fim:
            raise ValidationError('A data de início e a data de fim não podem ser idênticas.')

    def save(self, *args, **kwargs):
        # Força o Django a rodar as validações do clean() caso seja salvo via código
        self.full_clean()

        is_new = self.pk is None

        if is_new and self.status == 'C':
            self.status = 'P'

        # LÓGICA DE STATUS: Baseada no tempo (20 dias) e nos PDFs
        elif not is_new and self.status in ['P', 'C']:
            proxima_data = self.proxima_avaliacao_pendente

            if proxima_data:
                diferenca = (proxima_data - date.today()).days
                if diferenca <= 20:
                    self.status = 'P'
                else:
                    self.status = 'C'
            else:
                self.status = 'C'

        # Salva o pai
        super().save(*args, **kwargs)

        if is_new:
            self.gerar_cronograma()

        # LÓGICA DE RESCISÃO: O Exterminador de Avaliações Futuras
        if self.data_rescisao:
            # 1. Deleta todas as avaliações que estavam previstas para DEPOIS da rescisão
            self.avaliacao_semestrais.filter(data_prevista__gt=self.data_rescisao).delete()

            # 2. TRAVA DE SEGURANÇA: Se deletou tudo, recria pelo menos 1 (Avaliação de Desligamento)
            if not self.avaliacao_semestrais.exists():
                AvaliacaoSemestral.objects.create(
                    avaliacao_mae=self,
                    numero=1,
                    data_prevista=self.data_rescisao  # A data de cobrança vira o dia em que ele saiu
                )

    def gerar_cronograma(self):
        # ... (seu código de gerar o cronograma continua idêntico aqui) ...
        data_atual = self.data_inicio
        numero = 1
        while True:
            mes = data_atual.month + 6
            ano = data_atual.year
            if mes > 12:
                mes -= 12
                ano += 1
            dia = min(data_atual.day, calendar.monthrange(ano, mes)[1])
            nova_data = date(ano, mes, dia)

            if nova_data > self.data_fim:
                break

            AvaliacaoSemestral.objects.create(avaliacao_mae=self, numero=numero, data_prevista=nova_data)
            data_atual = nova_data
            numero += 1

        if numero == 1:
            AvaliacaoSemestral.objects.create(avaliacao_mae=self, numero=1, data_prevista=self.data_fim)

    @property
    def cor_status(self):
        # ... (continua idêntico) ...
        status_texto = str(self.status).strip()

        if status_texto == 'P':
            return 'primary'
        elif status_texto == 'C':
            return 'success'
        elif status_texto == 'ESE':
            return 'danger'
        else:
            return 'warning'

    @property
    def proxima_avaliacao_pendente(self):
        # ... (continua idêntico) ...
        proxima = self.avaliacao_semestrais.filter(
            models.Q(arquivo_pdf__exact='') | models.Q(arquivo_pdf__isnull=True)
        ).order_by('data_prevista').first()

        return proxima.data_prevista if proxima else None

    @property
    def urgencia_cor(self):
        # ... (continua idêntico, só corrigi um pequeno erro de digitação seu no "table-waring") ...
        proxima_data = self.proxima_avaliacao_pendente

        if not proxima_data or self.status in ['C', 'ESE']:
            return ''

        diferenca = (proxima_data - date.today()).days

        if diferenca < 0:
            return 'table-danger'
        elif diferenca <= 15:
            return 'table-warning'  # <-- corrigido o table-waring

        return ''

    def __str__(self):
        return f'{self.nome_estagiario}'


class AvaliacaoSemestral(models.Model):
    avaliacao_mae = models.ForeignKey(Avaliacao, on_delete=models.CASCADE, related_name='avaliacao_semestrais')
    numero = models.IntegerField()
    data_prevista = models.DateField()
    arquivo_pdf = models.FileField(upload_to='avaliacoes_pdfs/', blank=True, null=True)

    class Meta:
        ordering = ['data_prevista']

    @property
    def status(self):
        return 'Concluída' if self.arquivo_pdf else 'Pendente'
