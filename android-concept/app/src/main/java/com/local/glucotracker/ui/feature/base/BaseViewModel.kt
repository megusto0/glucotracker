package com.local.glucotracker.ui.feature.base

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.local.glucotracker.domain.model.OutboxKind
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.domain.model.Template
import com.local.glucotracker.domain.repository.OutboxRepository
import com.local.glucotracker.domain.repository.ProductsRepository
import com.local.glucotracker.ui.feature.mealentry.toProductMealKind
import com.local.glucotracker.ui.feature.mealentry.toTemplateMealKind
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

sealed interface BaseState {
    data object Loading : BaseState
    data class Ready(val items: List<BaseItem>, val filter: BaseFilter, val query: String) : BaseState
}

sealed interface BaseItem {
    data class Product(val product: com.local.glucotracker.domain.model.Product) : BaseItem
    data class Template(val template: com.local.glucotracker.domain.model.Template) : BaseItem
}

enum class BaseFilter {
    Frequent,
    Restaurants,
    Products,
    Templates,
    NeedsReview,
}

fun dedupTags(tags: List<String>): List<String> {
    val seen = mutableSetOf<String>()
    return tags.filter { seen.add(it) }
}

@HiltViewModel
class BaseViewModel @Inject constructor(
    private val productsRepository: ProductsRepository,
    private val outboxRepository: OutboxRepository,
) : ViewModel() {

    private val query = MutableStateFlow("")
    private val filter = MutableStateFlow(BaseFilter.Frequent)

    val state = combine(
        productsRepository.observeProducts(),
        productsRepository.observeTemplatesLocal(),
        query,
        filter,
    ) { cachedProducts, templates, q, f ->
            val items = buildItems(cachedProducts.value.orEmpty(), templates, q, f)
            BaseState.Ready(items = items, filter = f, query = q) as BaseState
        }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = BaseState.Loading,
        )

    fun setQuery(next: String) {
        query.value = next
    }

    fun setFilter(next: BaseFilter) {
        filter.value = next
    }

    fun useInJournal(item: BaseItem, onQueued: (String) -> Unit) {
        viewModelScope.launch {
            val outboxItem = outboxRepository.enqueue(item.toCreateMealKind())
            onQueued(outboxItem.id)
        }
    }
}

private fun buildItems(
    products: List<Product>,
    templates: List<Template>,
    query: String,
    filter: BaseFilter,
): List<BaseItem> {
    val q = query.trim().lowercase()
    val productItems = products.map { BaseItem.Product(it) }
    val templateItems = templates.map { BaseItem.Template(it) }
    val allItems = productItems + templateItems
    val filtered = when (filter) {
        BaseFilter.Frequent -> allItems.sortedByDescending { it.usageCount }
        BaseFilter.Restaurants -> productItems.filter { item ->
            item.product.kind.lowercase().contains("restaurant") || item.product.subtitle != null
        }
        BaseFilter.Products -> productItems
        BaseFilter.Templates -> templateItems
        BaseFilter.NeedsReview -> productItems.filter { item ->
            item.product.imageUrl == null || item.product.kcal == null || item.product.kcal == 0.0
        }
    }
    return if (q.isBlank()) filtered else filtered.filter { item ->
        val name = when (item) {
            is BaseItem.Product -> item.product.name
            is BaseItem.Template -> item.template.name
        }
        name.lowercase().contains(q)
    }
}

private val BaseItem.usageCount: Int
    get() = when (this) {
        is BaseItem.Product -> product.usageCount
        is BaseItem.Template -> template.usageCount
    }

private fun BaseItem.toCreateMealKind(): OutboxKind.CreateMeal =
    when (this) {
        is BaseItem.Product -> product.toProductMealKind()
        is BaseItem.Template -> template.toTemplateMealKind()
    }
