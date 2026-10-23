import unittest
from unittest.mock import AsyncMock, Mock

from app.mission_camera import MissionCamera


class CameraLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_failed_recorder_still_releases_server_process_and_log(self):
        camera = MissionCamera()
        camera.process = Mock(returncode=None)
        camera.process.wait = AsyncMock(return_value=-9)
        camera.call = AsyncMock(side_effect=RuntimeError('Recorder disconnected'))
        camera.runner = Mock(cleanup=AsyncMock())
        runner = camera.runner
        camera.log = Mock()
        with self.assertRaisesRegex(RuntimeError, 'Recorder disconnected'):
            await camera.close()
        camera.process.kill.assert_called_once()
        camera.process.wait.assert_awaited_once()
        runner.cleanup.assert_awaited_once()
        camera.log.close.assert_called_once()

    async def test_clean_finalization_closes_input_before_waiting(self):
        camera = MissionCamera()
        camera.process = Mock(returncode=None)
        async def finished():
            camera.process.stdin.close.assert_called_once()
            camera.process.returncode = 0
        camera.process.wait = AsyncMock(side_effect=finished)
        camera.call = AsyncMock(return_value={'video': {'error': None}, 'stats': {'errors': []}})
        await camera.close()
        camera.process.kill.assert_not_called()
