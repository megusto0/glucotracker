package com.local.glucotracker.healthconnect

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.local.glucotracker.R
import com.local.glucotracker.ui.design.GT
import com.local.glucotracker.ui.design.GTTheme

class HealthConnectRationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GTTheme {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(GT.space.lg),
                ) {
                    Text(
                        text = stringResource(R.string.health_connect_rationale_title),
                        color = GT.colors.ink,
                        style = GT.type.serifSection,
                    )
                    Text(
                        text = stringResource(R.string.health_connect_rationale_body),
                        color = GT.colors.ink2,
                        style = GT.type.sansBody,
                    )
                }
            }
        }
    }
}
