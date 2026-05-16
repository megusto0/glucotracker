package com.local.glucotracker.ui.navigation

import androidx.lifecycle.ViewModel
import com.local.glucotracker.ui.glucose.GlucoseSurfaces
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class AppConfigViewModel @Inject constructor(
    val navConfig: NavConfig,
    val flavorNavGraph: FlavorNavGraph,
    val glucoseSurfaces: GlucoseSurfaces,
) : ViewModel()
