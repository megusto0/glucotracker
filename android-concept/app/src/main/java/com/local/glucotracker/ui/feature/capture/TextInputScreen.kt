package com.local.glucotracker.ui.feature.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.local.glucotracker.R
import com.local.glucotracker.domain.model.Product
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider
import com.local.glucotracker.ui.design.primitives.GTOutlineButton
import com.local.glucotracker.ui.format.formatKcal
import kotlinx.coroutines.delay

@Composable
fun TextInputScreen(
    onFinished: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CaptureViewModel = hiltViewModel(),
) {
    var query by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Product>>(emptyList()) }
    var selectedProduct by remember { mutableStateOf<Product?>(null) }
    var weight by remember { mutableStateOf("") }
    val focusRequester = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current

    LaunchedEffect(query) {
        if (query.isBlank()) {
            results = emptyList()
            return@LaunchedEffect
        }
        delay(300)
        val current = query
        viewModel.searchProducts(current) { found ->
            if (current == query) {
                results = found
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(GT.colors.bg)
            .imePadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = GT.space.touch)
                .padding(horizontal = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onFinished) {
                Text(
                    text = "\u2190",
                    color = GT.colors.ink2,
                    style = GT.type.sansLabel,
                )
            }
            Text(
                text = stringResource(R.string.text_input_title),
                modifier = Modifier.padding(start = 4.dp),
                color = GT.colors.ink,
                style = GT.type.serifSection,
            )
        }
        GTHairlineDivider()

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = GT.space.lg, vertical = GT.space.sm)
                .background(GT.colors.surface, GT.shapes.card)
                .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                .padding(horizontal = GT.space.md, vertical = GT.space.sm),
        ) {
            if (query.isEmpty() && selectedProduct == null) {
                Text(
                    text = stringResource(R.string.text_input_hint),
                    color = GT.colors.muted,
                    style = GT.type.sansBody,
                )
            }
            BasicTextField(
                value = if (selectedProduct != null) selectedProduct!!.name else query,
                onValueChange = { new ->
                    if (selectedProduct != null) {
                        selectedProduct = null
                        weight = ""
                    }
                    query = new
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequester),
                textStyle = GT.type.sansBody.copy(
                    color = GT.colors.ink,
                ),
                cursorBrush = SolidColor(GT.colors.ink),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
                singleLine = true,
            )
        }

        LaunchedEffect(Unit) {
            focusRequester.requestFocus()
        }

        if (selectedProduct != null) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = GT.space.lg, vertical = GT.space.xs),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .background(GT.colors.surface, GT.shapes.card)
                        .border(GT.space.hairline, GT.colors.hairline, GT.shapes.card)
                        .padding(horizontal = GT.space.md, vertical = GT.space.sm),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        BasicTextField(
                            value = weight,
                            onValueChange = { weight = it },
                            modifier = Modifier.weight(1f),
                            textStyle = GT.type.monoLabel.copy(
                                color = GT.colors.ink,
                            ),
                            cursorBrush = SolidColor(GT.colors.ink),
                            keyboardOptions = KeyboardOptions(
                                keyboardType = KeyboardType.Number,
                                imeAction = ImeAction.Done,
                            ),
                            keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
                            singleLine = true,
                        )
                        Spacer(Modifier.width(GT.space.xs))
                        Text(
                            text = stringResource(R.string.text_input_weight_hint),
                            color = GT.colors.muted,
                            style = GT.type.monoLabel,
                        )
                    }
                    if (weight.isEmpty()) {
                        Text(
                            text = stringResource(R.string.text_input_weight_hint),
                            color = GT.colors.muted,
                            style = GT.type.monoLabel,
                        )
                    }
                }
            }
        } else if (results.isNotEmpty()) {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
            ) {
                items(results, key = { it.id }) { product ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                selectedProduct = product
                                query = product.name
                                weight = (product.defaultGrams ?: 100.0).let {
                                    if (it == it.toInt().toDouble()) it.toInt().toString() else it.toString()
                                }
                                results = emptyList()
                            }
                            .padding(horizontal = GT.space.lg, vertical = GT.space.md),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = product.name,
                                color = GT.colors.ink,
                                style = GT.type.sansLabel,
                                maxLines = 1,
                            )
                            if (product.subtitle != null) {
                                Text(
                                    text = product.subtitle,
                                    color = GT.colors.muted,
                                    style = GT.type.monoLabel,
                                    maxLines = 1,
                                )
                            }
                        }
                        product.kcal?.let { kcal ->
                            Text(
                                text = "${formatKcal(kcal)} ккал",
                                color = GT.colors.ink2,
                                style = GT.type.monoLabel,
                                maxLines = 1,
                            )
                        }
                    }
                    GTHairlineDivider(modifier = Modifier.padding(horizontal = GT.space.lg))
                }
            }
        } else {
            Spacer(Modifier.weight(1f))
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = GT.space.lg, vertical = GT.space.md),
            contentAlignment = Alignment.Center,
        ) {
            GTOutlineButton(
                text = stringResource(R.string.text_input_submit),
                onClick = {
                    val text = selectedProduct?.name ?: query
                    if (text.isBlank()) return@GTOutlineButton
                    val w = weight.toDoubleOrNull()
                    viewModel.enqueueTextMeal(text, w)
                    onFinished()
                },
                enabled = query.isNotBlank(),
            )
        }
    }
}
