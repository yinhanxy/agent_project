export const buildDepartmentSummaries = (departments = [], users = []) => {
  return departments.map((department) => {
    const members = users.filter((user) => user.dept_id === department.dept_id)
    const deptAdminCount = members.filter((user) => user.is_dept_admin).length

    return {
      ...department,
      members,
      memberCount: members.length,
      deptAdminCount,
      normalMemberCount: members.length - deptAdminCount,
    }
  })
}
