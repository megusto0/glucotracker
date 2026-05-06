package com.local.glucotracker.ui.feature.base

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import coil3.compose.AsyncImage
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTHintBox
import com.local.glucotracker.ui.design.primitives.GTPhotoSlot
import com.local.glucotracker.ui.design.primitives.GTPrimaryButton
import com.local.glucotracker.ui.design.primitives.GTTag
import com.local.glucotracker.ui.format.formatGrams
import com.local.glucotracker.ui.format.formatKcal
import com.local.glucotracker.ui.image.rememberApiImageModel

@Composable
fun BaseRoute(
    onOutboxQueued: (String) -> Unit,
    viewModel: BaseViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsState()
    BaseScreen(
        state = state,
        onQueryChange = viewModel::setQuery,
        onFilterChange = viewModel::setFilter,
        onUseInJournal = { item -> viewModel.useInJournal(item, onOutboxQueued) },
    )
}

@Composable
fun BaseScreen(
    state: BaseState,
    onQueryChange: (String) -> Unit,
    onFilterChange: (BaseFilter) -> Unit,
    onUseInJournal: (BaseItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    var detailItem by remember { mutableStateOf<BaseItem?>(null) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg),
    ) {
        Text(
            text = stringResource(R.string.base_title),
            modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
            color = GT.colors.ink,
            style = GT.type.serifTitle,
            maxLines = 1,
        )

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp)
                .height(44.dp)
                .background(GT.colors.surface, GT.shapes.card)
                .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                .padding(horizontal = 12.dp),
            contentAlignment = Alignment.CenterStart,
        ) {
            val queryText = if (state is BaseState.Ready) state.query else ""
            if (queryText.isBlank()) {
                Text(
                    text = stringResource(R.string.base_search_hint),
                    color = GT.colors.muted,
                    style = GT.type.sansBody,
                    maxLines = 1,
                )
            }
            BasicTextField(
                value = queryText,
                onValueChange = onQueryChange,
                textStyle = GT.type.sansBody.copy(color = GT.colors.ink),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Row(
            modifier = Modifier
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            BaseFilter.entries.forEach { f ->
                val label = filterLabel(f)
                val active = state is BaseState.Ready && state.filter == f
                Box(
                    modifier = Modifier
                        .heightIn(min = GT.space.touch)
                        .clickable { onFilterChange(f) },
                    contentAlignment = Alignment.Center,
                ) {
                    GTTag(text = label, active = active)
                }
            }
        }

        GTHairlineDivider(modifier = Modifier.padding(horizontal = 18.dp))

        if (state is BaseState.Ready) {
            if (state.items.isEmpty()) {
                Spacer(Modifier.weight(1f))
                GTHintBox(
                    text = stringResource(R.string.base_empty),
                    modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp),
                )
            } else {
                LazyColumn(
                    modifier = Modifier
                        .weight(1f)
                        .padding(horizontal = 18.dp, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(state.items, key = { item ->
                        when (item) {
                            is BaseItem.Product -> "p-${item.product.id}"
                            is BaseItem.Template -> "t-${item.template.id}"
                        }
                    }) { item ->
                        when (item) {
                            is BaseItem.Product -> ProductCard(
                                product = item.product,
                                onClick = { detailItem = item },
                            )
                            is BaseItem.Template -> TemplateCard(
                                template = item.template,
                                onClick = { detailItem = item },
                            )
                        }
                    }
                    item {
                        GTHintBox(
                            text = stringResource(R.string.base_desktop_hint),
                            modifier = Modifier.padding(vertical = 6.dp),
                        )
                        Spacer(Modifier.height(10.dp))
                    }
                }
            }
        } else {
            Spacer(Modifier.weight(1f))
        }
    }

    detailItem?.let { item ->
        DetailSheet(
            item = item,
            onUseInJournal = { selectedItem ->
                detailItem = null
                onUseInJournal(selectedItem)
            },
            onDismiss = { detailItem = null },
        )
    }
}

@Composable
private fun ProductCard(
    product: com.local.glucotracker.domain.model.Product,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        GTPhotoSlot(model = product.imageUrl, modifier = Modifier.size(32.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 10.dp),
        ) {
            Text(
                text = product.name,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                modifier = Modifier.padding(top = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                GTTag(text = product.kind)
                Spacer(Modifier.width(6.dp))
                Text(
                    text = stringResource(
                        R.string.base_product_macros,
                        formatGrams(product.proteinG ?: 0.0),
                        formatGrams(product.fatG ?: 0.0),
                        formatGrams(product.carbsG ?: 0.0),
                    ),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Column(horizontalAlignment = Alignment.End) {
            product.kcal?.let { kcal ->
                Text(
                    text = stringResource(R.string.base_product_kcal, formatKcal(kcal)),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
            Text(
                text = stringResource(R.string.base_usage_count, product.usageCount),
                modifier = Modifier.padding(top = 1.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun TemplateCard(
    template: com.local.glucotracker.domain.model.Template,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(GT.colors.surface, GT.shapes.card)
            .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        GTPhotoSlot(model = template.imageUrl, modifier = Modifier.size(32.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(start = 10.dp),
        ) {
            Text(
                text = template.name,
                color = GT.colors.ink,
                style = GT.type.sansLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = stringResource(
                    R.string.base_product_macros,
                    formatGrams(template.defaultProteinG ?: 0.0),
                    formatGrams(template.defaultFatG ?: 0.0),
                    formatGrams(template.defaultCarbsG ?: 0.0),
                ),
                modifier = Modifier.padding(top = 3.dp),
                color = GT.colors.ink2,
                style = GT.type.monoLabel,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            template.defaultKcal?.let { kcal ->
                Text(
                    text = stringResource(R.string.base_product_kcal, formatKcal(kcal)),
                    color = GT.colors.ink2,
                    style = GT.type.monoLabel,
                    maxLines = 1,
                )
            }
            Text(
                text = stringResource(R.string.base_usage_count, template.usageCount),
                modifier = Modifier.padding(top = 1.dp),
                color = GT.colors.muted,
                style = GT.type.monoLabel,
                maxLines = 1,
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DetailSheet(
    item: BaseItem,
    onUseInJournal: (BaseItem) -> Unit,
    onDismiss: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = GT.colors.surface,
        contentColor = GT.colors.ink,
        tonalElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 18.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (item) {
                is BaseItem.Product -> ProductDetail(product = item.product)
                is BaseItem.Template -> TemplateDetail(template = item.template)
            }
            GTPrimaryButton(
                text = stringResource(R.string.base_use_in_journal),
                onClick = { onUseInJournal(item) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ProductDetail(product: com.local.glucotracker.domain.model.Product) {
    Text(
        text = product.name,
        color = GT.colors.ink,
        style = GT.type.serifSection,
    )
    rememberApiImageModel(product.imageUrl)?.let { imageModel ->
        AsyncImage(
            model = imageModel,
            contentDescription = null,
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp),
            contentScale = ContentScale.Crop,
        )
    }
    GTTag(text = product.kind)
    Text(
        text = stringResource(
            R.string.base_product_macros,
            formatGrams(product.proteinG ?: 0.0),
            formatGrams(product.fatG ?: 0.0),
            formatGrams(product.carbsG ?: 0.0),
        ),
        color = GT.colors.ink2,
        style = GT.type.monoLabel,
    )
    product.kcal?.let { kcal ->
        Text(
            text = stringResource(R.string.base_product_kcal, formatKcal(kcal)),
            color = GT.colors.ink2,
            style = GT.type.monoLabel,
        )
    }
}

@Composable
private fun TemplateDetail(template: com.local.glucotracker.domain.model.Template) {
    Text(
        text = template.name,
        color = GT.colors.ink,
        style = GT.type.serifSection,
    )
    rememberApiImageModel(template.imageUrl)?.let { imageModel ->
        AsyncImage(
            model = imageModel,
            contentDescription = null,
            modifier = Modifier
                .fillMaxWidth()
                .height(180.dp),
            contentScale = ContentScale.Crop,
        )
    }
    Text(
        text = stringResource(
            R.string.base_product_macros,
            formatGrams(template.defaultProteinG ?: 0.0),
            formatGrams(template.defaultFatG ?: 0.0),
            formatGrams(template.defaultCarbsG ?: 0.0),
        ),
        color = GT.colors.ink2,
        style = GT.type.monoLabel,
    )
    template.defaultKcal?.let { kcal ->
        Text(
            text = stringResource(R.string.base_product_kcal, formatKcal(kcal)),
            color = GT.colors.ink2,
            style = GT.type.monoLabel,
        )
    }
}

@Composable
private fun filterLabel(filter: BaseFilter): String = when (filter) {
    BaseFilter.Frequent -> stringResource(R.string.base_filter_frequent)
    BaseFilter.Restaurants -> stringResource(R.string.base_filter_restaurants)
    BaseFilter.Products -> stringResource(R.string.base_filter_products)
    BaseFilter.Templates -> stringResource(R.string.base_filter_templates)
    BaseFilter.NeedsReview -> stringResource(R.string.base_filter_needs_review)
}
