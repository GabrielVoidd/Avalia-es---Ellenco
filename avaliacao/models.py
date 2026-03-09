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

    # Campo dos status com as opções pré-definidas
    status = models.CharField(max_length=3, choices=Status.choices)

    # Campo de observações
    observacoes = models.TextField(null=True, blank=True)

    data_criacao = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # --- A INTELIGÊNCIA VAI PARA O BANCO DE DADOS ---

        # 1. É um registro novo? É fisicamente impossível ter PDFs ainda.
        # Se a pessoa tentar marcar "Concluída" (C), forçamos para "Pendente" (P) na hora.
        if is_new and self.status == 'C':
            self.status = 'P'

        # 2. Já existe no banco e não é exceção ('ESE' ou 'SLR')? Auto-avalia as filhas.
        elif not is_new and self.status in ['P', 'C']:
            filhas = self.avaliacao_semestrais.all()
            # Só faz o cálculo se já existirem avaliações geradas
            if filhas.exists():
                todas_concluidas = all(bool(f.arquivo_pdf and f.arquivo_pdf.name) for f in filhas)
                self.status = 'C' if todas_concluidas else 'P'

        # ------------------------------------------------

        # Salva o registro pai no banco
        super().save(*args, **kwargs)

        # Se for novo, gera o cronograma de filhas (que nascem sem arquivo)
        if is_new:
            self.gerar_cronograma()

    def gerar_cronograma(self):
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

            # Cria a avaliação no banco já ligada a este estagiário
            AvaliacaoSemestral.objects.create(avaliacao_mae=self, numero=numero, data_prevista=nova_data)
            data_atual = nova_data
            numero += 1

        if numero == 1: # Se o período do estágio for menor que 6 meses
            AvaliacaoSemestral.objects.create(avaliacao_mae=self, numero=1, data_prevista=self.data_fim)

    @property
    def cor_status(self):
        # Pega o texto do status exatamente como está no banco
        status_texto = str(self.status).strip()

        if status_texto == 'P':
            return 'primary'  # Azul
        elif status_texto == 'C':
            return 'success'  # Verde
        elif status_texto == 'ESE':
            return 'danger'  # Vermelho
        else:
            return 'warning'  # Laranja (para o "Somente o link...")

    def __str__(self):
        return f'{self.nome_estagiario}'


class AvaliacaoSemestral(models.Model):
    avaliacao_mae = models.ForeignKey(Avaliacao, on_delete=models.CASCADE, related_name='avaliacao_semestrais')
    numero = models.IntegerField()
    data_prevista = models.DateField()
    arquivo_pdf = models.FileField(upload_to='avaliacoes_pdfs/', blank=True, null=True)

    @property
    def status(self):
        return 'Concluída' if self.arquivo_pdf else 'Pendente'
