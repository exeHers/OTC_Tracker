const fs = require("fs");
const path = require("path");

const gradlePath = path.join(
  __dirname,
  "..",
  "android",
  "capacitor-cordova-android-plugins",
  "build.gradle"
);

if (!fs.existsSync(gradlePath)) {
  console.log("No generated Capacitor Cordova Gradle file found.");
  process.exit(0);
}

const original = fs.readFileSync(gradlePath, "utf8");

const repositoriesBlock = `repositories {
    google()
    mavenCentral()
}`;

const dependenciesBlock = `dependencies {
    implementation fileTree(dir: 'src/main/libs', include: ['*.jar', '*.aar'])
    implementation fileTree(dir: 'libs', include: ['*.jar', '*.aar'])`;

let updated = original.replace(
  /repositories\s*\{\s*google\(\)\s*mavenCentral\(\)\s*flatDir\s*\{\s*dirs 'src\/main\/libs', 'libs'\s*\}\s*\}/m,
  repositoriesBlock
);

updated = updated.replace(
  /dependencies\s*\{\s*implementation fileTree\(dir: 'src\/main\/libs', include: \['\*\.jar'\]\)/m,
  dependenciesBlock
);

if (updated !== original) {
  fs.writeFileSync(gradlePath, updated, "utf8");
  console.log("Patched Capacitor Gradle file to remove flatDir.");
} else {
  console.log("Capacitor Gradle file already patched.");
}
