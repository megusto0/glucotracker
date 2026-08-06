package com.local.glucotracker.ui.glucose

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.primitives.GTHairlineDivider

/**
 * A card action written in the app's own voice.
 *
 * These were outlined pill buttons — the heaviest shape the app owns — sitting
 * inside cards built from hairlines, monospace kickers and muted meta. One was
 * loud; two stacked read as a form rather than a journal entry. Same tap
 * target, none of the weight: the label is set like the kickers already
 * running along the top of the same card.
 */
@Composable
fun GlucoCardAction(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .heightIn(min = GT.space.touch)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(
            text = text.uppercase(),
            color = GT.colors.ink2,
            style = GT.type.kicker,
            maxLines = 1,
        )
    }
}

/**
 * The footer of a card, holding its actions under a hairline.
 *
 * Flows rather than sits on a fixed line. A card-wide footer fits two actions
 * side by side, but the same pair inside a single dish's meta column has the
 * photo and the time gutter taken out of its width, and the second label was
 * being clipped to one letter. It wraps there instead.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GlucoCardActionRow(
    modifier: Modifier = Modifier,
    horizontalPadding: Dp = 14.dp,
    content: @Composable RowScope.() -> Unit,
) {
    GTHairlineDivider(modifier = Modifier.padding(horizontal = horizontalPadding))
    FlowRow(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = horizontalPadding),
        horizontalArrangement = Arrangement.spacedBy(20.dp),
        verticalArrangement = Arrangement.Center,
        content = content,
    )
}
