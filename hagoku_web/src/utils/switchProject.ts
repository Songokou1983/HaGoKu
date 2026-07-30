/** 项目切换统一入口。所有切换都走这个函数。 */
export function switchToProject(
  name: string,
  send: (cmd: string, payload?: unknown) => boolean,
  setCurrentProject: (p: string) => void,
) {
  setCurrentProject(name);
  send("switch_project", { project: name });
}
