import pytest

from contrapartes.models import Contraparte, Habilitacao, StatusHabilitacao


@pytest.fixture
def contraparte(db):
    """Perfil validado: sem isso não há contrato (AGENTS.md D29)."""
    contraparte = Contraparte.objects.create(nome="Contratante Fictício", documento="58974790890")
    Habilitacao.objects.create(contraparte=contraparte, status=StatusHabilitacao.HABILITADA)
    return contraparte
