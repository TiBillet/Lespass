from django.http import Http404, HttpResponse
from django.utils.translation import gettext_lazy as _

def test_404(request):
    """
    View that raises a 404 error to test the 404 error template.
    """
    raise Http404(_("This is a test 404 error"))

def test_500(request):
    """
    View that raises a 500 error to test the 500 error template.
    """
    raise ValueError("Coucou paske prout")

    # Deliberately cause a division by zero error
    # 1 / 0
    # return HttpResponse("This should not be displayed")
