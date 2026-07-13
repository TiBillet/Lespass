# ViewSet Patterns — Exemples Complets

Exemples complets de ViewSets avec différents cas d'usage.

---

## Pattern 1: CRUD Complet avec HTMX

ViewSet avec list, detail, create, update, delete — tout en HTML/HTMX.

```python
from rest_framework import viewsets, permissions, serializers, status
from rest_framework.decorators import action
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.messages import get_messages
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json


class ArticleSerializer(serializers.Serializer):
    """
    Validation explicite pour Article.
    Explicit validation for Article.
    """
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(required=False, allow_blank=True)
    is_published = serializers.BooleanField(required=False, default=False)
    
    def validate_title(self, value):
        title_cleaned = value.strip()
        if len(title_cleaned) < 5:
            raise serializers.ValidationError(
                'Titre trop court (min 5 caracteres) / Title too short (min 5 chars)'
            )
        return title_cleaned


class ArticleViewSet(viewsets.ViewSet):
    """
    ViewSet complet pour les articles de blog.
    Complete ViewSet for blog articles.
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    # ========== LIST ==========
    def list(self, request):
        """
        Liste paginee des articles.
        Paginated list of articles.
        """
        # Parametres de pagination explicites
        # Explicit pagination parameters
        page_number_from_request = request.GET.get('page', 1)
        articles_per_page = 20
        
        # Requete explicite
        # Explicit query
        all_articles = Article.objects.select_related('author').all()
        articles_published = all_articles.filter(is_published=True)
        articles_ordered_by_date = articles_published.order_by('-created_at')
        
        # Pagination manuelle explicite
        # Explicit manual pagination
        from django.core.paginator import Paginator
        paginator = Paginator(articles_ordered_by_date, articles_per_page)
        page_of_articles = paginator.get_page(page_number_from_request)
        
        return render(request, "articles/list.html", {
            'articles_page': page_of_articles,
            'total_count': paginator.count
        })
    
    # ========== RETRIEVE ==========
    def retrieve(self, request, pk=None):
        """
        Detail d'un article.
        Article detail.
        """
        article = get_object_or_404(
            Article.objects.select_related('author'),
            uuid=pk
        )
        
        # Articles similaires (5 max)
        # Similar articles (max 5)
        articles_with_same_category = Article.objects.filter(
            category=article.category,
            is_published=True
        ).exclude(uuid=pk)[:5]
        
        return render(request, "articles/detail.html", {
            'article': article,
            'similar_articles': articles_with_same_category
        })
    
    # ========== CREATE ==========
    @method_decorator(login_required)
    def create(self, request):
        """
        Creation d'un article (formulaire + traitement).
        Create an article (form + processing).
        """
        if request.method == 'GET':
            # Affiche le formulaire vide
            # Display empty form
            categories_available = Category.objects.all()
            return render(request, "articles/form.html", {
                'categories': categories_available
            })
        
        # POST: traitement du formulaire
        # POST: form processing
        serializer = ArticleSerializer(data=request.POST)
        
        if serializer.is_valid():
            article_created = Article.objects.create(
                title=serializer.validated_data['title'],
                content=serializer.validated_data.get('content', ''),
                is_published=serializer.validated_data.get('is_published', False),
                author=request.user,
                created_at=timezone.now()
            )
            
            messages.add_message(
                request, 
                messages.SUCCESS,
                'Article cree avec succes / Article created successfully'
            )
            
            # Redirect vers le detail (POST-redirect-GET)
            # Redirect to detail (POST-redirect-GET)
            return redirect('article-detail', pk=article_created.uuid)
        
        # Erreurs de validation — retourne le formulaire avec erreurs
        # Validation errors — return form with errors
        categories_available = Category.objects.all()
        return render(request, "articles/form.html", {
            'categories': categories_available,
            'form_errors': serializer.errors,
            'form_data': request.POST
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # ========== UPDATE ==========
    @method_decorator(login_required)
    def update(self, request, pk=None):
        """
        Mise a jour complete d'un article (PUT).
        Full article update (PUT).
        """
        article = get_object_or_404(Article, uuid=pk)
        
        # Verification des permissions
        # Permission check
        if article.author != request.user and not request.user.is_staff:
            return render(request, "errors/403.html", status=403)
        
        if request.method == 'GET':
            categories_available = Category.objects.all()
            return render(request, "articles/form.html", {
                'article': article,
                'categories': categories_available,
                'is_update': True
            })
        
        # PUT processing
        serializer = ArticleSerializer(data=request.POST)
        
        if serializer.is_valid():
            article.title = serializer.validated_data['title']
            article.content = serializer.validated_data.get('content', '')
            article.is_published = serializer.validated_data.get('is_published', False)
            article.updated_at = timezone.now()
            article.save()
            
            messages.add_message(request, messages.SUCCESS, 'Article mis a jour / Article updated')
            return redirect('article-detail', pk=article.uuid)
        
        categories_available = Category.objects.all()
        return render(request, "articles/form.html", {
            'article': article,
            'categories': categories_available,
            'form_errors': serializer.errors,
            'is_update': True
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # ========== DESTROY ==========
    @method_decorator(login_required)
    def destroy(self, request, pk=None):
        """
        Suppression d'un article avec confirmation.
        Delete an article with confirmation.
        """
        article = get_object_or_404(Article, uuid=pk)
        
        if article.author != request.user and not request.user.is_staff:
            return render(request, "errors/403.html", status=403)
        
        if request.method == 'GET':
            # Page de confirmation
            # Confirmation page
            return render(request, "articles/confirm_delete.html", {
                'article': article
            })
        
        # DELETE confirmed
        article_title_for_message = article.title
        article.delete()
        
        messages.add_message(
            request, 
            messages.SUCCESS,
            f'"{article_title_for_message}" supprime / deleted'
        )
        
        # Si requete HTMX, retourne un trigger pour toast + redirection
        # If HTMX request, return trigger for toast + redirect
        if request.headers.get('HX-Request'):
            messages_list = get_messages(request)
            toast_payload = [{"level": m.level_tag, "text": str(m)} for m in messages_list]
            
            response = render(request, "articles/partials/empty.html")
            response["HX-Trigger"] = json.dumps({
                "toast": {"items": toast_payload},
                "redirect": {"url": "/articles/"}
            })
            return response
        
        return redirect('article-list')
    
    # ========== CUSTOM ACTIONS ==========
    
    @action(detail=True, methods=["POST"])
    @method_decorator(login_required)
    def toggle_publish(self, request, pk=None):
        """
        Bascule publication/prive d'un article.
        Toggle publish/private status.
        """
        article = get_object_or_404(Article, uuid=pk)
        
        if article.author != request.user:
            return render(request, "errors/403.html", status=403)
        
        # Inverse le statut
        # Toggle status
        article.is_published = not article.is_published
        article.save(update_fields=['is_published'])
        
        message_text = (
            'Article publie / Article published' 
            if article.is_published 
            else 'Article mis en prive / Article set to private'
        )
        messages.add_message(request, messages.SUCCESS, message_text)
        
        # Retourne le bouton mis a jour
        # Return updated button
        return render(request, "articles/partials/publish_toggle.html", {
            'article': article
        })
    
    @action(detail=False, methods=["GET"])
    def search(self, request):
        """
        Recherche en temps reel (pour HTMX).
        Real-time search (for HTMX).
        """
        query_from_user = request.GET.get('q', '').strip()
        
        if len(query_from_user) < 2:
            return render(request, "articles/partials/search_results.html", {
                'articles': [],
                'query': query_from_user,
                'message': 'Tapez au moins 2 caracteres / Type at least 2 characters'
            })
        
        # Recherche dans titre et contenu
        # Search in title and content
        from django.db.models import Q
        articles_matching = Article.objects.filter(
            Q(title__icontains=query_from_user) | 
            Q(content__icontains=query_from_user),
            is_published=True
        )[:10]
        
        return render(request, "articles/partials/search_results.html", {
            'articles': articles_matching,
            'query': query_from_user,
            'count': len(articles_matching)
        })
```

---

## Pattern 2: ViewSet Read-Only (API + Templates)

Pour des données en lecture seule avec différentes représentations.

```python
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from django.shortcuts import render, get_object_or_404


class ProductViewSet(viewsets.ViewSet):
    """
    ViewSet en lecture seule pour les produits.
    Read-only ViewSet for products.
    """
    permission_classes = [permissions.AllowAny]
    
    def list(self, request):
        """
        Liste des produits avec filtrage.
        Product list with filtering.
        """
        # Filtres explicites depuis les parametres GET
        # Explicit filters from GET parameters
        category_filter = request.GET.get('category')
        min_price_filter = request.GET.get('min_price')
        max_price_filter = request.GET.get('max_price')
        
        # Construction de la requete etape par etape
        # Step-by-step query building
        products_base_query = Product.objects.filter(is_active=True)
        
        if category_filter:
            products_base_query = products_base_query.filter(
                category__slug=category_filter
            )
        
        if min_price_filter:
            try:
                min_price_value = float(min_price_filter)
                products_base_query = products_base_query.filter(
                    price__gte=min_price_value
                )
            except ValueError:
                # Prix invalide — on ignore le filtre
                # Invalid price — ignore filter
                pass
        
        if max_price_filter:
            try:
                max_price_value = float(max_price_filter)
                products_base_query = products_base_query.filter(
                    price__lte=max_price_value
                )
            except ValueError:
                pass
        
        products_ordered = products_base_query.order_by('name')
        
        # Categories pour le filtre
        # Categories for filter
        all_categories = Category.objects.filter(is_active=True)
        
        return render(request, "products/list.html", {
            'products': products_ordered,
            'categories': all_categories,
            'current_filters': {
                'category': category_filter,
                'min_price': min_price_filter,
                'max_price': max_price_filter
            }
        })
    
    def retrieve(self, request, pk=None):
        """
        Detail d'un produit avec produits similaires.
        Product detail with similar products.
        """
        product = get_object_or_404(
            Product.objects.select_related('category'),
            slug=pk
        )
        
        # Produits de la meme categorie (exclusion du courant)
        # Same category products (exclude current)
        similar_products_in_category = Product.objects.filter(
            category=product.category,
            is_active=True
        ).exclude(slug=pk)[:4]
        
        return render(request, "products/detail.html", {
            'product': product,
            'similar_products': similar_products_in_category
        })
    
    @action(detail=True, methods=["GET"])
    def quick_view(self, request, pk=None):
        """
        Vue rapide pour modal HTMX.
        Quick view for HTMX modal.
        """
        product = get_object_or_404(Product, slug=pk)
        
        return render(request, "products/partials/quick_view.html", {
            'product': product
        })
    
    @action(detail=False, methods=["GET"])
    def by_category(self, request):
        """
        Liste groupee par categorie.
        List grouped by category.
        """
        categories_with_products = Category.objects.filter(
            products__is_active=True
        ).distinct().prefetch_related('products')
        
        return render(request, "products/by_category.html", {
            'categories': categories_with_products
        })
```

---

## Pattern 3: ViewSet avec Relations Complexes

Gestion des relations many-to-many et foreign keys.

```python
from rest_framework import viewsets, serializers
from django.shortcuts import render, get_object_or_404
from django.db import transaction


class OrderCreateSerializer(serializers.Serializer):
    """
    Validation pour la creation de commande.
    Validation for order creation.
    """
    customer_name = serializers.CharField(max_length=100)
    customer_email = serializers.EmailField()
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        error_messages={
            'min_length': 'Au moins un article / At least one item required'
        }
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_items(self, items_data):
        """
        Validation que chaque item a product_id et quantity.
        Validate that each item has product_id and quantity.
        """
        items_validated = []
        
        for index, item in enumerate(items_data):
            product_id = item.get('product_id')
            quantity = item.get('quantity')
            
            if not product_id:
                raise serializers.ValidationError(
                    f'Item {index}: product_id manquant / missing'
                )
            
            try:
                quantity_as_int = int(quantity)
                if quantity_as_int < 1:
                    raise ValueError()
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    f'Item {index}: quantite invalide / invalid quantity'
                )
            
            # Verification que le produit existe
            # Check product exists
            try:
                product = Product.objects.get(id=product_id, is_active=True)
            except Product.DoesNotExist:
                raise serializers.ValidationError(
                    f'Item {index}: produit inexistant / product not found'
                )
            
            items_validated.append({
                'product': product,
                'quantity': quantity_as_int,
                'unit_price': product.price
            })
        
        return items_validated


class OrderViewSet(viewsets.ViewSet):
    """
    ViewSet pour les commandes avec gestion des lignes.
    ViewSet for orders with line items.
    """
    
    def list(self, request):
        orders = Order.objects.select_related('customer').prefetch_related(
            'items', 'items__product'
        ).order_by('-created_at')
        
        # Filtre par statut
        # Filter by status
        status_filter = request.GET.get('status')
        if status_filter:
            orders = orders.filter(status=status_filter)
        
        return render(request, "orders/list.html", {
            'orders': orders,
            'status_choices': Order.STATUS_CHOICES
        })
    
    def retrieve(self, request, pk=None):
        order = get_object_or_404(
            Order.objects.select_related('customer').prefetch_related(
                'items', 'items__product'
            ),
            uuid=pk
        )
        
        # Calcul du total (pourrait etre une propriete du modele)
        # Calculate total (could be a model property)
        total_amount = sum(
            item.quantity * item.unit_price 
            for item in order.items.all()
        )
        
        return render(request, "orders/detail.html", {
            'order': order,
            'total_calculated': total_amount
        })
    
    def create(self, request):
        if request.method == 'GET':
            products_available = Product.objects.filter(is_active=True)
            return render(request, "orders/form.html", {
                'products': products_available
            })
        
        serializer = OrderCreateSerializer(data=request.POST)
        
        if serializer.is_valid():
            with transaction.atomic():
                # Creation de la commande
                # Create order
                order = Order.objects.create(
                    customer_name=serializer.validated_data['customer_name'],
                    customer_email=serializer.validated_data['customer_email'],
                    notes=serializer.validated_data.get('notes', ''),
                    status='pending'
                )
                
                # Creation des lignes de commande
                # Create order items
                items_to_create = []
                for item_data in serializer.validated_data['items']:
                    items_to_create.append(OrderItem(
                        order=order,
                        product=item_data['product'],
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price']
                    ))
                
                OrderItem.objects.bulk_create(items_to_create)
            
            messages.add_message(request, messages.SUCCESS, 'Commande creee / Order created')
            return redirect('order-detail', pk=order.uuid)
        
        products_available = Product.objects.filter(is_active=True)
        return render(request, "orders/form.html", {
            'products': products_available,
            'form_errors': serializer.errors,
            'form_data': request.POST
        }, status=400)
```

---

## Pattern 4: Action avec Mise a Jour Partielle (HTMX)

Pour les interactions rapides sans rechargement.

```python
from rest_framework.decorators import action
from django.views.decorators.http import require_http_methods


class TaskViewSet(viewsets.ViewSet):
    """
    Gestion de taches avec actions rapides HTMX.
    Task management with quick HTMX actions.
    """
    
    @action(detail=True, methods=["POST"])
    def complete(self, request, pk=None):
        """
        Marquer une tache comme completee.
        Mark task as completed.
        """
        task = get_object_or_404(Task, uuid=pk)
        
        # Verification proprietaire
        # Check ownership
        if task.assigned_to != request.user:
            return render(request, "errors/403.html", status=403)
        
        task.is_completed = True
        task.completed_at = timezone.now()
        task.save(update_fields=['is_completed', 'completed_at'])
        
        # Retourne la carte mise a jour pour remplacement HTMX
        # Return updated card for HTMX replacement
        return render(request, "tasks/partials/task_card.html", {
            'task': task
        })
    
    @action(detail=True, methods=["POST"])
    def reorder(self, request, pk=None):
        """
        Reordonner une tache (drag & drop).
        Reorder a task (drag & drop).
        """
        task = get_object_or_404(Task, uuid=pk)
        
        new_position_from_request = request.POST.get('new_position')
        
        try:
            new_position_as_int = int(new_position_from_request)
        except (ValueError, TypeError):
            return render(request, "errors/400.html", status=400)
        
        # Logique de reordonnancement
        # Reordering logic
        old_position = task.position
        
        with transaction.atomic():
            if new_position_as_int < old_position:
                # Monte dans la liste — decaler les autres vers le bas
                # Moving up — shift others down
                Task.objects.filter(
                    project=task.project,
                    position__gte=new_position_as_int,
                    position__lt=old_position
                ).update(position=models.F('position') + 1)
            else:
                # Descend dans la liste — decaler les autres vers le haut
                # Moving down — shift others up
                Task.objects.filter(
                    project=task.project,
                    position__gt=old_position,
                    position__lte=new_position_as_int
                ).update(position=models.F('position') - 1)
            
            task.position = new_position_as_int
            task.save(update_fields=['position'])
        
        # Retourne OK silencieux pour HTMX
        # Return silent OK for HTMX
        return render(request, "tasks/partials/empty.html")
    
    @action(detail=False, methods=["GET"])
    def filter_by_status(self, request):
        """
        Filtrer les taches par statut (HTMX).
        Filter tasks by status (HTMX).
        """
        status_filter = request.GET.get('status', 'all')
        
        tasks_base_query = Task.objects.filter(assigned_to=request.user)
        
        if status_filter == 'completed':
            tasks_filtered = tasks_base_query.filter(is_completed=True)
        elif status_filter == 'pending':
            tasks_filtered = tasks_base_query.filter(is_completed=False)
        else:
            tasks_filtered = tasks_base_query
        
        tasks_ordered = tasks_filtered.order_by('position')
        
        return render(request, "tasks/partials/task_list.html", {
            'tasks': tasks_ordered,
            'current_filter': status_filter
        })
```
