import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val signingPropertiesPath = providers.environmentVariable("BISNU_SIGNING_PROPERTIES")
    .orNull
    ?.takeIf(String::isNotBlank)
val signingPropertiesFile = if (signingPropertiesPath == null) {
    rootProject.file("../../key.properties")
} else {
    rootProject.file(signingPropertiesPath)
}
val signingProperties = Properties()
if (signingPropertiesFile.isFile) {
    signingPropertiesFile.inputStream().use(signingProperties::load)
}

val releaseRequested = gradle.startParameter.taskNames.any {
    it.contains("release", ignoreCase = true)
}
if (releaseRequested && !signingPropertiesFile.isFile) {
    throw GradleException(
        "Release signing is not configured. Add a local key.properties file."
    )
}

android {
    namespace = "app.bisnux.mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "app.bisnux.mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["usesCleartextTraffic"] = "false"
    }

    if (signingPropertiesFile.isFile) {
        signingConfigs {
            create("release") {
                val configuredStore = File(
                    signingProperties.getProperty("storeFile")
                        ?: throw GradleException("storeFile is missing from key.properties.")
                )
                storeFile = if (configuredStore.isAbsolute) {
                    configuredStore
                } else {
                    rootProject.file("../..").resolve(configuredStore)
                }
                storePassword = signingProperties.getProperty("storePassword")
                    ?: throw GradleException("storePassword is missing from key.properties.")
                keyAlias = signingProperties.getProperty("keyAlias")
                    ?: throw GradleException("keyAlias is missing from key.properties.")
                keyPassword = signingProperties.getProperty("keyPassword")
                    ?: throw GradleException("keyPassword is missing from key.properties.")
            }
        }
    }

    buildTypes {
        debug {
            manifestPlaceholders["usesCleartextTraffic"] = "true"
        }
        release {
            manifestPlaceholders["usesCleartextTraffic"] = "false"
            if (signingPropertiesFile.isFile) {
                signingConfig = signingConfigs.getByName("release")
            }
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
