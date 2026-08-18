package com.local.glucotracker.ui.stock

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.ui.design.primitives.GTTag

/**
 * Where a row came from, when it came from stock rather than the catalogue.
 *
 * Shared by База and the search sheet because the two lists show the same
 * entries and a mark that appears on one of them is worse than no mark: it
 * reads as a property of the screen instead of a property of the food.
 */
@Composable
fun stockLabel(product: Product): String? = when (product.sourceKind) {
    "fridge" -> stringResource(R.string.base_stock_fridge)
    "meal_prep" -> stringResource(R.string.base_stock_mealprep)
    else -> null
}

@Composable
fun StockTag(product: Product) {
    stockLabel(product)?.let { label -> GTTag(text = label) }
}
