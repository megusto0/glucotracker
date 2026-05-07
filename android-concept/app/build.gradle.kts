plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.kapt)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.hilt)
    alias(libs.plugins.paparazzi)
}

val openApiGenerator by configurations.creating
val openApiSpec = rootProject.layout.projectDirectory.file("../docs/openapi.yaml")
val openApiSpecPath = openApiSpec.asFile.absolutePath.replace('\\', '/')
val generatedOpenApiDir = layout.buildDirectory.dir("generated/openapi")
val generatedOpenApiKotlinDir = generatedOpenApiDir.map { it.dir("src/main/kotlin") }

android {
    namespace = "com.local.glucotracker"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.local.glucotracker"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    sourceSets {
        getByName("main") {
            java.srcDir(generatedOpenApiKotlinDir)
        }
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
    }
}

kapt {
    correctErrorTypes = true
}

tasks.register<JavaExec>("generateApiClient") {
    group = "code generation"
    description = "Generate the Kotlin/Ktor OpenAPI client from docs/openapi.yaml."

    classpath = openApiGenerator
    mainClass.set("org.openapitools.codegen.OpenAPIGenerator")
    args(
        "generate",
        "-g",
        "kotlin",
        "-i",
        openApiSpecPath,
        "-o",
        generatedOpenApiDir.get().asFile.absolutePath,
        "--library",
        "jvm-ktor",
        "--package-name",
        "com.local.glucotracker.generated",
        "--api-package",
        "com.local.glucotracker.generated.api",
        "--model-package",
        "com.local.glucotracker.generated.model",
        "--additional-properties",
        listOf(
            "serializationLibrary=kotlinx_serialization",
            "dateLibrary=kotlinx-datetime",
            "collectionType=list",
            "enumPropertyNaming=UPPERCASE",
        ).joinToString(","),
    )

    inputs.file(openApiSpec)
    outputs.dir(generatedOpenApiDir)

    doLast {
        val generatedRoot = generatedOpenApiKotlinDir.get().asFile
        generatedRoot.walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .forEach { file ->
                var text = file.readText()
                text = text
                    .replace(
                        "kotlin.collections.List<@Contextual kotlin.Any>",
                        "kotlin.collections.List<kotlinx.serialization.json.JsonElement>",
                    )
                    .replace(
                        "kotlin.collections.Map<kotlin.String, kotlin.Any>",
                        "kotlin.collections.Map<kotlin.String, kotlinx.serialization.json.JsonElement>",
                    )

                if (file.name == "ApiClient.kt") {
                    text = text
                        .replace(
                            "import io.ktor.client.plugins.contentnegotiation.ContentNegotiation\n",
                            "import io.ktor.client.plugins.contentnegotiation.ContentNegotiation\n" +
                                "import io.ktor.client.plugins.DefaultRequest\n" +
                                "import io.ktor.client.request.header\n" +
                                "import io.ktor.serialization.kotlinx.json.json\n" +
                                "import com.local.glucotracker.data.api.OpenApiJson\n",
                        )
                        .replace(
                            "it.install(ContentNegotiation) {\n            }\n",
                            "it.install(ContentNegotiation) {\n                json(OpenApiJson.json)\n            }\n" +
                                "            it.install(DefaultRequest) {\n                header(\"Authorization\", \"Bearer dev\")\n            }\n",
                        )
                }

                file.writeText(text)
            }
    }
}

tasks.named("preBuild") {
    dependsOn("generateApiClient")
}

dependencies {
    openApiGenerator(libs.openapi.generator.cli)

    implementation(libs.core.ktx)
    implementation(libs.activity.compose)
    implementation(libs.navigation.compose)
    implementation(libs.hilt.navigation.compose)
    implementation(libs.lifecycle.viewmodel.ktx)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)

    implementation(libs.hilt.android)
    kapt(libs.hilt.compiler)

    implementation(libs.ktor.core)
    implementation(libs.ktor.content.negotiation)
    implementation(libs.ktor.serialization.json)
    implementation(libs.ktor.logging)
    implementation(libs.ktor.android)
    implementation(libs.ktor.auth)

    implementation(libs.kotlinx.serialization.json)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    kapt(libs.room.compiler)

    implementation(libs.datastore)
    implementation(libs.datastore.preferences)

    implementation(libs.workmanager)

    implementation(libs.camerax.core)
    implementation(libs.camerax.camera2)
    implementation(libs.camerax.lifecycle)
    implementation(libs.camerax.view)

    implementation(libs.coil.compose)
    implementation(libs.coil.network.ktor)

    implementation(libs.kotlinx.datetime)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.junit)
    testImplementation(libs.turbine)
    testImplementation(libs.coroutines.test)
    testImplementation(libs.ktor.mock)
    testImplementation(libs.compose.ui.test.junit4)

    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.androidx.test.ext)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.coroutines.test)
    androidTestImplementation(libs.turbine)
    androidTestImplementation(libs.compose.ui.test.junit4)
}
