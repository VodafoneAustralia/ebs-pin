pipeline {
  agent { label "cdk" }
  options {
    timestamps()
    parallelsAlwaysFailFast()
    preserveStashes()
  }

  stages {
    stage('Validate') {
      stage('Sonarqube Analysis'){
        steps {
          script {
            scannerHome = tool 'sonar-scanner'
          }
          withSonarQubeEnv('sonarqube server') {
            sh "${scannerHome}/bin/sonar-scanner \
              -Dsonar.projectKey=ebs-pin" 
          }
          sleep(5)
          timeout(time: 15, unit: 'SECONDS') {
            waitForQualityGate abortPipeline: true
          }
        }
      }
    }
  }
}
