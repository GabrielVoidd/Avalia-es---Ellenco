from django import forms
from django.forms import inlineformset_factory
from .models import Avaliacao, AvaliacaoSemestral

class AvaliacaoForm(forms.ModelForm):
    class Meta:
        model = Avaliacao
        exclude = ['data_criacao']
        widgets = {
            'nome_estagiario': forms.TextInput(attrs={'class': 'form-control'}),
            'empresa': forms.TextInput(attrs={'class': 'form-control'}),
            'instituicao_ensino': forms.TextInput(attrs={'class': 'form-control'}),
            'data_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'data_fim': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'data_rescisao': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

# Formulário para as filhas (Só vai mostrar o campo do PDF)
class AvaliacaoSemestralForm(forms.ModelForm):
    class Meta:
        model = AvaliacaoSemestral
        fields = ['arquivo_pdf']
        widgets = {
            'arquivo_pdf': forms.FileInput(attrs={'class': 'form-control form-control-sm'})
        }

# O FormSet junta tudo para a tela de Edição
AvaliacaoFormSet = inlineformset_factory(
    Avaliacao, AvaliacaoSemestral,
    form=AvaliacaoSemestralForm,
    extra=0, # Não deixa criar datas novas manualmente, só usar as geradas
    can_delete=False # Impede de apagar as datas geradas
)