package com.local.glucotracker.ui.design.primitives

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.format.PhotoProcessingFailureStep
import com.local.glucotracker.ui.format.PhotoProcessingStage
import com.local.glucotracker.ui.format.PhotoProcessingUiState

@Composable
fun GTPhotoProcessingPipeline(
    state: PhotoProcessingUiState,
    modifier: Modifier = Modifier,
) {
    val steps = pipelineSteps(state)
    Column(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            steps.forEachIndexed { index, step ->
                PipelineDot(state = step)
                if (index < steps.lastIndex) {
                    PipelineLine(
                        complete = step == PipelineStepState.Complete &&
                            steps[index + 1] != PipelineStepState.Pending,
                        failed = step == PipelineStepState.Failed ||
                            steps[index + 1] == PipelineStepState.Failed,
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 5.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            val labels = labelsFor(state)
            labels.forEach { label ->
                Text(
                    text = label,
                    modifier = Modifier.weight(1f),
                    color = GT.colors.muted,
                    style = GT.type.sansLabel.copy(fontSize = 10.5.sp),
                    textAlign = TextAlign.Center,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
fun GTPhotoProcessingProgressBar(
    progress: Float?,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(4.dp)
            .background(GT.colors.hairline, GT.shapes.tag),
    ) {
        val width = progress?.coerceIn(0f, 1f) ?: 0.36f
        Box(
            modifier = Modifier
                .fillMaxWidth(width)
                .height(4.dp)
                .background(GT.colors.accent.copy(alpha = if (progress == null) 0.34f else 0.7f), GT.shapes.tag),
        )
    }
}

private enum class PipelineStepState {
    Complete,
    Active,
    Pending,
    Failed,
}

@Composable
private fun PipelineDot(state: PipelineStepState) {
    val fill = when (state) {
        PipelineStepState.Complete -> GT.colors.accent.copy(alpha = 0.82f)
        PipelineStepState.Active -> GT.colors.surface
        PipelineStepState.Pending -> GT.colors.surface
        PipelineStepState.Failed -> GT.colors.surface
    }
    val border = when (state) {
        PipelineStepState.Complete -> GT.colors.accent.copy(alpha = 0.82f)
        PipelineStepState.Active -> GT.colors.accent.copy(alpha = 0.74f)
        PipelineStepState.Pending -> GT.colors.hairline2
        PipelineStepState.Failed -> GT.colors.warn
    }
    Box(
        modifier = Modifier
            .size(12.dp)
            .background(fill, CircleShape)
            .border(GT.space.hairline, border, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        when (state) {
            PipelineStepState.Active -> Box(
                modifier = Modifier
                    .size(5.dp)
                    .background(GT.colors.accent.copy(alpha = 0.7f), CircleShape),
            )
            PipelineStepState.Failed -> Text(
                text = "!",
                color = GT.colors.warn,
                style = GT.type.monoLabel.copy(fontSize = 8.sp),
                maxLines = 1,
            )
            else -> Unit
        }
    }
}

@Composable
private fun PipelineLine(
    complete: Boolean,
    failed: Boolean,
    modifier: Modifier = Modifier,
) {
    val color: Color = when {
        failed -> GT.colors.warn.copy(alpha = 0.56f)
        complete -> GT.colors.accent.copy(alpha = 0.46f)
        else -> GT.colors.hairline2
    }
    Spacer(Modifier.width(3.dp))
    Box(
        modifier = modifier
            .height(GT.space.hairline)
            .background(color),
    )
    Spacer(Modifier.width(3.dp))
}

private fun pipelineSteps(state: PhotoProcessingUiState): List<PipelineStepState> =
    when (state.stage) {
        PhotoProcessingStage.Captured,
        PhotoProcessingStage.WaitingUpload,
        -> listOf(
            PipelineStepState.Complete,
            PipelineStepState.Pending,
            PipelineStepState.Pending,
            PipelineStepState.Pending,
        )
        PhotoProcessingStage.Uploading -> listOf(
            PipelineStepState.Complete,
            PipelineStepState.Active,
            PipelineStepState.Pending,
            PipelineStepState.Pending,
        )
        PhotoProcessingStage.Estimating -> listOf(
            PipelineStepState.Complete,
            PipelineStepState.Complete,
            PipelineStepState.Active,
            PipelineStepState.Pending,
        )
        PhotoProcessingStage.Done -> listOf(
            PipelineStepState.Complete,
            PipelineStepState.Complete,
            PipelineStepState.Complete,
            PipelineStepState.Complete,
        )
        PhotoProcessingStage.Stuck -> when (state.failureStep) {
            PhotoProcessingFailureStep.Estimate -> listOf(
                PipelineStepState.Complete,
                PipelineStepState.Complete,
                PipelineStepState.Failed,
                PipelineStepState.Pending,
            )
            else -> listOf(
                PipelineStepState.Complete,
                PipelineStepState.Failed,
                PipelineStepState.Pending,
                PipelineStepState.Pending,
            )
        }
    }

private fun labelsFor(state: PhotoProcessingUiState): List<String> =
    listOf(
        "снято",
        if (state.stage == PhotoProcessingStage.Estimating ||
            state.stage == PhotoProcessingStage.Done ||
            state.failureStep == PhotoProcessingFailureStep.Estimate
        ) {
            "отправлено"
        } else {
            "отправка"
        },
        "оценка",
        "готово",
    )
