import json
import traceback
import logging

from rest_framework.views import APIView
from rest_framework.response import Response

from nexus.zeroshot.client import InvokeModel
from nexus.zeroshot.api.permissions import ZeroshotTokenPermission
from nexus.usecases.logs.entities import ZeroshotDTO
from nexus.usecases.logs.create import CreateZeroshotLogsUseCase


logger = logging.getLogger(__name__)


class ZeroShotFastPredictAPIView(APIView):

    authentication_classes = []
    permission_classes = [ZeroshotTokenPermission]

    def post(self, request):
        data = request.data
        try:
            invoke_model = InvokeModel(data)
            response = invoke_model.invoke()
            zeroshot_dto = ZeroshotDTO(
                text=data.get("text"),
                classification=response["output"].get("classification"),
                other=response["output"].get("other", False),
                options=data.get("options"),
                nlp_log=str(json.dumps(response)),
                language=data.get("language")
            )
            CreateZeroshotLogsUseCase().create(zeroshot_dto)
            return Response(status=200, data=response if response.get("output") else {"error": response})
        except Exception as error:
            traceback.print_exc()
            logger.error(f"[ - ] Zeroshot fast predict: {error}")
            return Response(status=500, data={"error": str(error)})
