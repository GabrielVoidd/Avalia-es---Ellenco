from django.urls import path
from . import views

app_name = 'avaliacao'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('novo/', views.nova_avaliacao, name='nova_avaliacao'),
    path('registros/', views.lista_avaliacoes, name='lista_avaliacoes'),
    path('editar/<int:pk>/', views.editar_avaliacao, name='editar_avaliacao'),
    path('exportar/', views.exportar_csv, name='exportar_csv'),
    path('excluir/<int:pk>/', views.deletar_avaliacao, name='deletar_avaliacao'),
    path('remover-pdf/<int:pk>/', views.remover_pdf_avaliacao, name='remover_pdf_avaliacao'),
    path('exportar-pdf/', views.exportar_pdf, name='exportar_pdf'),
    # path('avaliacao/<int:pk>/historico/', views.historico_avaliacao, name='historico_avaliacao'),
    path('auditoria/avaliacoes/', views.historico_geral_avaliacoes, name='historico_geral_avaliacoes'),
]