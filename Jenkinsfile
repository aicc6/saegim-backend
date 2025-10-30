pipeline {
    agent any

    // 파라미터 정의 (수동 빌드 시 브랜치 선택 가능)
    parameters {
        choice(
            name: 'BRANCH_TO_BUILD',
            choices: ['develop', 'main', 'release/latest'],
            description: '빌드할 브랜치를 선택하세요 (GitHub Webhook에서는 자동 감지)'
        )
        booleanParam(
            name: 'RUN_TESTS',
            defaultValue: true,
            description: '테스트 실행 여부'
        )
        booleanParam(
            name: 'SKIP_MIGRATIONS',
            defaultValue: false,
            description: '데이터베이스 마이그레이션 스킵 여부'
        )
    }

    // 빌드 트리거 설정
    triggers {
        githubPush()
    }

    // 환경 변수 설정
    environment {
        // Git Repository 설정 (Public Repository)
        GIT_REPOSITORY_URL = 'https://github.com/aicc6/saegim-backend.git'

        // Docker Registry 설정
        DOCKER_REGISTRY = "${env.CUSTOM_DOCKER_REGISTRY}"
        DOCKER_CREDENTIALS = "${env.CUSTOM_DOCKER_CREDENTIALS}"
        DOCKER_IMAGE = 'aicc/saegim-backend'
        CONTAINER_NAME = 'saegim-backend'

        // Python 실행 환경 설정
        PYTHON_VERSION = '3.11.13'
        PYTHONUNBUFFERED = '1'
        PYTHONDONTWRITEBYTECODE = '1'
        PIP_NO_CACHE_DIR = '1'

        // 애플리케이션 환경
        APP_ENV = 'production'
    }

    // 빌드 옵션
    options {
        buildDiscarder(logRotator(
            numToKeepStr: '10',
            daysToKeepStr: '30'
        ))
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()
        timestamps()
    }

    stages {
        // 1. 소스 코드 체크아웃 및 환경 설정
        stage('🔄 Clone Repository & Setup') {
            steps {
                // SCM에서 소스 코드 체크아웃
                checkout scm

                script {
                    echo "🚀 Saegim 배포 빌드 시작"

                    // Jenkins가 자동으로 감지한 브랜치 정보 출력 + 디버깅
                    echo "📋 BRANCH_NAME: ${env.BRANCH_NAME}"
                    echo "📋 GIT_BRANCH: ${env.GIT_BRANCH}"
                    echo "📋 GIT_LOCAL_BRANCH: ${env.GIT_LOCAL_BRANCH}"
                    echo "📋 CHANGE_BRANCH: ${env.CHANGE_BRANCH}"
                    echo "📋 파라미터 BRANCH_TO_BUILD: ${params.BRANCH_TO_BUILD}"
                    echo "🔖 커밋: ${env.GIT_COMMIT}"
                    echo "📂 Git Repository: ${env.GIT_REPOSITORY_URL}"

                    // 브랜치 이름 결정 로직 개선 (GitHub Webhook 우선)
                    def currentBranch = ''

                    // 1. GitHub Webhook에서 오는 정보를 최우선으로 확인
                    if (env.GIT_BRANCH) {
                        currentBranch = env.GIT_BRANCH
                        echo "✅ GIT_BRANCH에서 감지: ${currentBranch}"
                    }
                    else if (env.BRANCH_NAME) {
                        currentBranch = env.BRANCH_NAME
                        echo "✅ BRANCH_NAME에서 감지: ${currentBranch}"
                    }
                    else if (env.CHANGE_BRANCH) {
                        currentBranch = env.CHANGE_BRANCH
                        echo "✅ CHANGE_BRANCH에서 감지: ${currentBranch}"
                    }
                    // 2. 파라미터는 수동 빌드 시에만 사용 (기본값이 아닌 경우)
                    else if (params.BRANCH_TO_BUILD && params.BRANCH_TO_BUILD != 'develop') {
                        currentBranch = params.BRANCH_TO_BUILD
                        echo "✅ 파라미터에서 브랜치 선택: ${currentBranch}"
                    }
                    // 3. 기본값
                    else {
                        currentBranch = 'develop'
                        echo "⚠️ 브랜치 감지 실패, 기본값 사용: ${currentBranch}"
                    }

                    // 브랜치 이름 정리 (refs/heads/, origin/ 제거)
                    if (currentBranch?.startsWith('refs/heads/')) {
                        currentBranch = currentBranch.replace('refs/heads/', '')
                    }
                    if (currentBranch?.startsWith('origin/')) {
                        currentBranch = currentBranch.replace('origin/', '')
                    }

                    echo "🔍 최종 브랜치: ${currentBranch}"
                    env.CURRENT_BRANCH = currentBranch

                    // Git 정보 가져오기
                    env.GIT_COMMIT_SHORT = sh(
                        script: "git rev-parse --short HEAD",
                        returnStdout: true
                    ).trim()

                    echo "✅ 브랜치 감지 완료: ${env.CURRENT_BRANCH}"
                }

                // 환경별 .env 파일 생성
                script {
                    // 실제 체크아웃된 브랜치 정보 사용
                    def currentBranch = env.CURRENT_BRANCH ?: 'develop'
                    def envType = currentBranch.contains('main') ? 'production' : 'development'
                    def credentialsId = "saegim-backend"

                    echo "🌿 현재 브랜치: ${currentBranch}"
                    echo "🏗️ 환경 설정: ${envType}"

                    try {
                        withCredentials([
                            file(credentialsId: credentialsId, variable: 'ENV_FILE')
                        ]) {
                            sh """
                                echo "📄 환경 변수 파일 복사 중"
                                cp "\$ENV_FILE" .env
                                chmod 644 .env
                                echo "✅ 환경 변수 파일 생성 완료"
                            """
                        }
                    } catch (Exception e) {
                        echo "⚠️ 환경 변수 파일 로드 실패, 기본 환경 설정 사용: ${e.getMessage()}"
                        sh """
                            echo "📄 기본 환경 변수 파일 생성 중"
                            echo "APP_ENV=${envType}" > .env
                            echo "BUILD_TIME=\$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> .env
                            echo "GIT_COMMIT=${env.GIT_COMMIT_SHORT}" >> .env
                            echo "BUILD_NUMBER=${BUILD_NUMBER}" >> .env
                            echo "APP_PORT=8000" >> .env
                            chmod 644 .env
                            echo "✅ 기본 환경 변수 파일 생성 완료"
                        """
                    }
                }
            }
        }

        // 2. Docker 이미지 빌드
        stage('🐳 Build Docker Image') {
            steps {
                script {
                    echo "🐳 Docker 이미지 빌드 시작"

                    try {
                        def app = docker.build("${DOCKER_IMAGE}:${BUILD_NUMBER}")
                        env.DOCKER_BUILD_SUCCESS = 'true'

                        echo "✅ Docker 이미지 빌드 성공"
                        echo "📦 이미지: ${DOCKER_IMAGE}:${BUILD_NUMBER}"
                    } catch (Exception e) {
                        env.DOCKER_BUILD_SUCCESS = 'false'
                        error "Docker 빌드 실패: ${e.getMessage()}"
                    }
                }
            }
        }

        // 3. Docker 이미지 푸시
        // stage('📤 Push Docker Image') {
        //     when {
        //         environment name: 'DOCKER_BUILD_SUCCESS', value: 'true'
        //     }
        //     steps {
        //         script {
        //             try {
        //                 // Docker 레지스트리가 설정되어 있고 로컬이 아닌 경우에만 푸시
        //                 if (env.DOCKER_REGISTRY && env.DOCKER_REGISTRY != 'localhost' && env.DOCKER_REGISTRY != 'local') {
        //                     docker.withRegistry("https://${DOCKER_REGISTRY}", "${DOCKER_CREDENTIALS}") {
        //                         def app = docker.image("${DOCKER_IMAGE}:${BUILD_NUMBER}")
        //                         app.push("${BUILD_NUMBER}")

        //                         // main 브랜치는 latest 태그도 푸시
        //                         def currentBranch = env.CURRENT_BRANCH ?: 'develop'
        //                         if (currentBranch.contains('main')) {
        //                             app.push("latest")
        //                             echo "✅ latest 태그 푸시 완료"
        //                         }
        //                     }
        //                     echo "✅ Docker 이미지 푸시 성공: ${DOCKER_IMAGE}:${BUILD_NUMBER}"
        //                 } else {
        //                     echo "ℹ️ 로컬 Docker 이미지 사용, 원격 레지스트리 푸시 스킵"
        //                 }

        //                 env.DOCKER_PUSH_SUCCESS = 'true'
        //                 echo "✅ Docker 이미지 푸시 성공: ${DOCKER_IMAGE}:${BUILD_NUMBER}"
        //             } catch (Exception e) {
        //                 error "Docker 푸시 실패: ${e.getMessage()}"
        //             }
        //         }
        //     }
        // }

        // 5. Docker 컨테이너 배포
        stage('🚀 Deploy') {
            // when {
            //     environment name: 'DOCKER_PUSH_SUCCESS', value: 'true'
            // }
            steps {
                script {
                    def currentBranch = env.CURRENT_BRANCH ?: 'develop'
                    def deployEnv = currentBranch.contains('main') ? 'production' : 'development'
                    def containerName = "${CONTAINER_NAME}-${deployEnv}"
                    def dockerNetwork = 'saegim-net'

                    echo "🚀 배포 시작: ${deployEnv} 환경"
                    echo "🌿 현재 브랜치: ${currentBranch}"
                    echo "📦 컨테이너: ${containerName}"
                    echo "🌐 네트워크: ${dockerNetwork}"
                    echo "📦 이미지: ${DOCKER_IMAGE}:${BUILD_NUMBER}"

                    sh """
                        # Docker 네트워크 확인 및 생성
                        echo "🌐 Docker 네트워크 확인: ${dockerNetwork}"
                        if ! docker network ls | grep -q ${dockerNetwork}; then
                            echo "🔧 네트워크 ${dockerNetwork} 생성 중..."
                            docker network create ${dockerNetwork} || echo "네트워크 생성 실패 (이미 존재하거나 권한 부족)"
                        else
                            echo "✅ 네트워크 ${dockerNetwork} 존재 확인"
                        fi

                        # 원격 레지스트리에서 이미지 다운로드 (로컬이 아닌 경우)
                        #if [[ "${DOCKER_REGISTRY}" != "localhost" && "${DOCKER_REGISTRY}" != "local" ]]; then
                        #    echo "📥 원격 이미지 다운로드: ${DOCKER_IMAGE}:${BUILD_NUMBER}"
                        #    docker pull ${DOCKER_IMAGE}:${BUILD_NUMBER}
                        #else
                        #    echo "ℹ️ 로컬 Docker 이미지 사용"
                        #fi

                        # 기존 컨테이너 중지 및 삭제
                        docker stop ${containerName} || true
                        docker rm ${containerName} || true

                        # 새 컨테이너 실행
                        docker run -d \\
                            --name ${containerName} \\
                            --network ${dockerNetwork} \\
                            --restart unless-stopped \\
                            --label "app=saegim-backend" \\
                            --health-cmd="curl -f http://localhost:8000/ || exit 1" \\
                            --health-interval=30s \\
                            --health-timeout=10s \\
                            --health-retries=3 \\
                            -p 9000:49000 \\
                            ${DOCKER_IMAGE}:${BUILD_NUMBER}

                        # 이전 이미지 정리 (선택사항)
                        docker image prune -f
                    """
                }
            }
        }
    }

    // 빌드 후 작업
    post {
        always {
            echo "📋 빌드 후 정리 작업"

            script {
                try {
                    sh 'docker system prune -f'
                } catch (Exception e) {
                    echo "Docker 정리 실패: ${e.getMessage()}"
                }
            }

            cleanWs()
        }

        success {
            echo '✅ 파이프라인 완료!'
            script {
                def currentBranch = env.CURRENT_BRANCH ?: 'develop'
                def deployEnv = currentBranch.contains('main') ? 'production' : 'development'
                echo "🌐 Saegim Backend 애플리케이션이 ${deployEnv} 환경에 배포되었습니다"
                echo "📚 배포된 이미지: ${DOCKER_IMAGE}:${BUILD_NUMBER}"
                echo "🔖 빌드 정보: 브랜치=${currentBranch}, 커밋=${env.GIT_COMMIT_SHORT}, 빌드=${BUILD_NUMBER}"
            }
        }

        failure {
            echo '❌ 파이프라인 실패!'

            script {
                // 실패 시 디버깅 정보 출력
                sh '''
                    echo "🔍 디버깅 정보:"
                    docker ps -a | grep saegim-backend || echo "관련 컨테이너 없음"
                    docker images | grep saegim-backend || echo "관련 이미지 없음"
                '''
            }
        }

        unstable {
            echo '⚠️ Saegim Backend 배포 파이프라인 불안정 (테스트/품질 검사 경고)'
        }
    }
}
